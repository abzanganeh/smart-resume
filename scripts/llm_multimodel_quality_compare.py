#!/usr/bin/env python3
"""Compare GPT-4o-mini, GPT-4.1-mini, GPT-5-mini, Gemini Flash on rewrite + cover letter."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

# Load shared eval helpers from sibling script
_spec = importlib.util.spec_from_file_location(
    "llm_eval",
    Path(__file__).resolve().parent / "llm_model_quality_eval.py",
)
_llm_eval = importlib.util.module_from_spec(_spec)
sys.modules["llm_eval"] = _llm_eval
assert _spec.loader is not None
_spec.loader.exec_module(_llm_eval)

from app.llm.base import LLMClient, LLMMessage, LLMResponse  # noqa: E402
from app.llm.factory import get_llm_client  # noqa: E402
from app.llm.pricing import estimate_cost  # noqa: E402

OUT = Path(__file__).resolve().parent / "eval_results" / "multimodel_quality_compare.json"

# User pricing ($/1M tokens) for cost estimates when not in pricing.py
USER_RATES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-5-mini": (0.25, 2.00),
    "gemini-2.5-flash": (0.30, 2.50),  # published 2.5 rate (model unavailable on key)
    "gemini-3.5-flash": (1.50, 9.00),
}


class OpenAIGpt5Adapter(LLMClient):
    """OpenAI adapter using max_completion_tokens (required for gpt-5-mini)."""

    def __init__(self, model: str, api_key: str) -> None:
        import openai

        self._model = model
        self._client = openai.AsyncOpenAI(api_key=api_key)

    @property
    def context_window(self) -> int:
        return 128_000

    @property
    def supports_structured_output(self) -> bool:
        return True

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        response_schema: dict | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        kwargs: dict = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_completion_tokens": max_tokens,
            "store": False,
        }
        if response_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "strict": False, "schema": response_schema},
            }
        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
            model=self._model,
            provider="openai",
        )

    async def stream(self, messages, *, max_tokens: int = 4096, temperature: float = 0.2):
        raise NotImplementedError


COMPARE_ARMS: tuple[_llm_eval.ModelArm, ...] = (
    _llm_eval.ModelArm("gpt-4o-mini", "openai", "gpt-4o-mini", api_key_env="OPENAI_API_KEY"),
    _llm_eval.ModelArm("gpt-4.1-mini", "openai", "gpt-4.1-mini", api_key_env="OPENAI_API_KEY"),
    _llm_eval.ModelArm("gpt-5-mini", "openai-gpt5", "gpt-5-mini", api_key_env="OPENAI_API_KEY"),
    # gemini-2.5-flash returns 404 on current key — 3.5 Flash is the available Flash successor
    _llm_eval.ModelArm("gemini-3.5-flash", "gemini", "gemini-3.5-flash"),
)


def _est_cost(model: str, inp: int = 8000, out: int = 2500) -> float:
    rates = USER_RATES.get(model)
    if not rates:
        return estimate_cost(inp, out, "openai" if model.startswith("gpt") else "gemini", model)
    return round((inp / 1_000_000) * rates[0] + (out / 1_000_000) * rates[1], 6)


def _resolve_compare_client(arm: _llm_eval.ModelArm) -> LLMClient | None:
    if arm.provider == "openai-gpt5":
        key = os.environ.get("OPENAI_API_KEY", "")
        if len(key) < 20:
            return None
        return OpenAIGpt5Adapter(arm.model, key)
    return _llm_eval._resolve_client(arm)


async def _run_arm(case: dict, arm: _llm_eval.ModelArm, judge: LLMClient) -> dict:
    client = _resolve_compare_client(arm)
    if client is None:
        return {"arm": arm.label, "skipped": True, "reason": "no API key"}
    session = _llm_eval._build_session(case)
    queue: asyncio.Queue = asyncio.Queue()
    import app.agent.phase3_rewrite as phase3_rewrite

    phase3_rewrite.ensure_session_company_intel = _llm_eval._noop_company_intel  # type: ignore[method-assign]
    try:
        tailored = await _llm_eval._run_phase3_with_quality_gate(session, client, queue)
    except Exception as exc:
        return {"arm": arm.label, "model": arm.model, "error": str(exc)}

    session.phase3_output = tailored
    from app.models.session import PhaseStatus

    session.phase3_status = PhaseStatus.done
    try:
        cover = await _llm_eval.cover_letter_agent.run(session, client, queue, tone="balanced")
    except Exception as exc:
        return {"arm": arm.label, "model": arm.model, "error": f"cover: {exc}"}

    must = case["must_have"]
    score = _llm_eval.compute_score_result(tailored, must, career_stage=case["career_stage"])
    bullets = [b for exp in tailored.experience for b in exp.bullets]
    judge_scores = await _llm_eval._judge_rewrite(
        judge, case=case, model_label=arm.label, summary=tailored.summary, experience_bullets=bullets
    )
    avg = sum(judge_scores[k] for k in ("jd_alignment", "factual_fidelity", "writing_quality", "ats_readiness")) / 4
    return {
        "arm": arm.label,
        "model": arm.model,
        "pricing_input_per_1m": USER_RATES.get(arm.model, (None, None))[0],
        "pricing_output_per_1m": USER_RATES.get(arm.model, (None, None))[1],
        "est_phase3_cost_usd": _est_cost(arm.model, 8000, 2500),
        "est_cover_cost_usd": _est_cost(arm.model, 6000, 900),
        "ats_score": score.ats_score,
        "missing_keywords": len(score.missing_keywords),
        "experience_bullets": len(bullets),
        "skills_count": len(tailored.skills),
        "skills_categorized": _llm_eval._skills_category_ok(tailored.skills),
        "cover_words": cover.word_count,
        "cover_in_range": 250 <= (cover.word_count or 0) <= 420,
        "judge_avg": round(avg, 2),
        "judge": judge_scores,
        "summary_preview": tailored.summary[:200],
    }


async def main() -> None:
    _llm_eval._load_keys()
    os.environ.setdefault("OPENAI_API_KEY", _llm_eval._env.get("OPENAI_API_KEY", ""))
    judge = get_llm_client("gemini", "gemini-3.5-flash")

    results = {
        "note": (
            "gemini-2.5-flash is unavailable (404) on current API key; "
            "gemini-3.5-flash is the comparable Flash-tier Gemini model."
        ),
        "cases": [],
    }
    for case in _llm_eval.EVAL_CASES:
        row = {"case_id": case["id"], "arms": []}
        print(f"\n=== {case['id']} ===", flush=True)
        for arm in COMPARE_ARMS:
            print(f"  {arm.label}...", flush=True)
            r = await _run_arm(case, arm, judge)
            row["arms"].append(r)
            if r.get("judge_avg"):
                print(
                    f"    judge={r['judge_avg']} ATS={r['ats_score']} bullets={r['experience_bullets']} "
                    f"cover={r['cover_words']}w est_p3={r['est_phase3_cost_usd']*100:.2f}¢",
                    flush=True,
                )
            else:
                print(f"    {r.get('error') or r.get('reason')}", flush=True)
        results["cases"].append(row)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT}", flush=True)

    # Aggregate table
    print("\n--- AGGREGATE (avg across 2 cases) ---")
    print(f"{'Model':<18} {'Judge':>6} {'ATS':>5} {'Bullets':>7} {'CoverW':>7} {'P3¢':>6}")
    for arm in COMPARE_ARMS:
        rows = []
        for case in results["cases"]:
            for a in case["arms"]:
                if a.get("arm") == arm.label and a.get("judge_avg"):
                    rows.append(a)
        if not rows:
            print(f"{arm.label:<18} {'N/A':>6}")
            continue
        print(
            f"{arm.label:<18} "
            f"{sum(r['judge_avg'] for r in rows)/len(rows):>6.2f} "
            f"{sum(r['ats_score'] for r in rows)/len(rows):>5.0f} "
            f"{sum(r['experience_bullets'] for r in rows)/len(rows):>7.1f} "
            f"{sum(r['cover_words'] for r in rows)/len(rows):>7.0f} "
            f"{sum(r['est_phase3_cost_usd'] for r in rows)/len(rows)*100:>6.2f}"
        )


if __name__ == "__main__":
    asyncio.run(main())
