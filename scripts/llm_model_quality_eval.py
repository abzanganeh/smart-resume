#!/usr/bin/env python3
"""Compare LLM quality for phase-3 rewrite + cover letter across model tiers.

Usage (from repo root):
  cd backend && GOOGLE_API_KEY=$GEMINI_API_KEY python ../scripts/llm_model_quality_eval.py

Optional: DEEPSEEK_API_KEY for the third arm.
Results: scripts/eval_results/model_quality_latest.json
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

# backend package imports
BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from dotenv import dotenv_values  # noqa: E402

_env = dotenv_values(BACKEND / ".env")


def _load_keys() -> None:
    gemini = _env.get("GEMINI_API_KEY") or _env.get("GOOGLE_API_KEY") or ""
    if gemini and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = gemini
    deepseek = _env.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")
    if deepseek and not os.environ.get("DEEPSEEK_API_KEY"):
        os.environ["DEEPSEEK_API_KEY"] = deepseek


_load_keys()

from app.agent import cover_letter as cover_letter_agent  # noqa: E402
from app.agent import phase3_rewrite  # noqa: E402
from app.agent.phase4_deterministic import compute_score_result  # noqa: E402
from app.llm.base import LLMClient, LLMMessage  # noqa: E402
from app.llm.factory import get_llm_client  # noqa: E402
from app.llm.pricing import estimate_cost  # noqa: E402
from app.llm.structured import complete_structured  # noqa: E402
from app.models.audit import AuditOutput, KeywordCoverage  # noqa: E402
from app.models.keywords import Keyword, KeywordExtractionOutput, RoleContext  # noqa: E402
from app.models.session import PhaseStatus, Session  # noqa: E402
from app.models.userinfo import UserInfo  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "eval_results"
JUDGE_MODEL = ("gemini", "gemini-3.5-flash")


@dataclass(frozen=True)
class ModelArm:
    label: str
    provider: str
    model: str
    base_url: str | None = None
    api_key_env: str | None = None


MODEL_ARMS: tuple[ModelArm, ...] = (
    ModelArm("gemini-flash", "gemini", "gemini-3.5-flash"),
    ModelArm("gemini-flash-lite", "gemini", "gemini-3.5-flash-lite"),
    ModelArm(
        "deepseek-v4-flash",
        "deepseek",
        "deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
    ),
)


CASE_BACKEND = {
    "id": "backend_engineer",
    "resume": (
        "Jane Doe\nBackend Engineer\njane.doe@email.com | San Francisco, CA\n\n"
        "SUMMARY\nBackend engineer with 6 years building APIs and data services.\n\n"
        "EXPERIENCE\n"
        "Acme Corp — Senior Backend Engineer | 2020–Present\n"
        "- Built Python FastAPI services handling 2M requests/day.\n"
        "- Designed PostgreSQL schemas and optimized slow queries.\n"
        "- Deployed services on Kubernetes with CI/CD pipelines.\n\n"
        "Beta Labs — Software Engineer | 2017–2020\n"
        "- Maintained REST APIs in Django and Redis caching layer.\n"
        "- Collaborated with product on feature delivery.\n\n"
        "SKILLS\nPython, FastAPI, PostgreSQL, Redis, Docker, Git\n"
    ),
    "jd": (
        "Backend Engineer — Acme Payments\n\n"
        "We need a backend engineer to build scalable Python APIs.\n"
        "Requirements: Python, FastAPI, PostgreSQL, Kubernetes, CI/CD pipelines, "
        "REST APIs, distributed systems, 5+ years experience.\n"
        "Nice to have: Redis, observability, cloud-native architectures.\n"
    ),
    "must_have": [
        "Python",
        "FastAPI",
        "PostgreSQL",
        "Kubernetes",
        "CI/CD pipelines",
        "REST APIs",
        "distributed systems",
    ],
    "career_stage": "senior",
    "target_role": "Backend Engineer",
}

CASE_PM = {
    "id": "product_manager",
    "resume": (
        "Alex Rivera\nProduct Manager\nalex.rivera@email.com | Austin, TX\n\n"
        "EXPERIENCE\n"
        "Nimbus Health — Senior Product Manager | 2019–Present\n"
        "- Owned roadmap for patient scheduling platform used by 40 clinics.\n"
        "- Ran discovery interviews and shipped onboarding improvements.\n"
        "- Partnered with engineering on API integrations and HIPAA workflows.\n\n"
        "Orbit Retail — Product Manager | 2016–2019\n"
        "- Launched mobile checkout reducing cart abandonment.\n"
        "- Defined KPIs and ran A/B tests with analytics team.\n\n"
        "SKILLS\nRoadmapping, stakeholder management, SQL, Jira, user research\n"
    ),
    "jd": (
        "Senior Product Manager — Growth Platform\n\n"
        "Lead product for a B2B SaaS growth platform.\n"
        "Must have: product roadmap, stakeholder management, user research, "
        "A/B testing, SQL, cross-functional leadership, SaaS experience.\n"
        "Nice to have: API integrations, HIPAA, analytics.\n"
    ),
    "must_have": [
        "product roadmap",
        "stakeholder management",
        "user research",
        "A/B testing",
        "SQL",
        "cross-functional leadership",
        "SaaS",
    ],
    "career_stage": "senior",
    "target_role": "Senior Product Manager",
}

EVAL_CASES = (CASE_BACKEND, CASE_PM)


class DeepSeekAdapter:
    """Minimal OpenAI-compatible client for DeepSeek eval runs."""

    def __init__(self, model: str, api_key: str, base_url: str) -> None:
        import openai

        self._model = model
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

    @property
    def context_window(self) -> int:
        return 128_000

    @property
    def supports_structured_output(self) -> bool:
        return False

    @property
    def provider_name(self) -> str:
        return "deepseek"

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
    ) -> object:
        from app.llm.base import LLMResponse

        kwargs: dict = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_schema:
            kwargs["response_format"] = {"type": "json_object"}
        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
            model=self._model,
            provider="deepseek",
        )

    async def stream(self, messages: list[LLMMessage], *, max_tokens: int = 4096, temperature: float = 0.2):
        raise NotImplementedError


def _build_session(case: dict) -> Session:
    must = [
        Keyword(
            term=t,
            source_sentence=f"Required: {t}",
            category="tool",
            tier="must_have",
            reason="JD requirement",
        )
        for t in case["must_have"]
    ]
    phase1 = KeywordExtractionOutput(
        must_have_keywords=must,
        role_context=RoleContext(career_level="senior", primary_domain=case["target_role"]),
    )
    phase2 = AuditOutput(
        keyword_coverage=KeywordCoverage(
            present=["Python"] if case["id"] == "backend_engineer" else ["roadmapping"],
            missing_must_have=case["must_have"][:3],
            missing_nice_to_have=[],
        ),
        overall_score=62,
        summary="Resume needs stronger JD keyword placement and metrics.",
    )
    return Session(
        session_id=str(uuid.uuid4()),
        resume_raw=case["resume"],
        jd_raw=case["jd"],
        user_info=UserInfo(
            name="Jane Doe" if case["id"] == "backend_engineer" else "Alex Rivera",
            target_role=case["target_role"],
            career_stage=case["career_stage"],
        ),
        phase1_output=phase1,
        phase2_output=phase2,
        phase1_status=PhaseStatus.done,
        phase2_status=PhaseStatus.done,
    )


def _resolve_client(arm: ModelArm) -> LLMClient | None:
    if arm.provider == "deepseek":
        key = os.environ.get(arm.api_key_env or "", "") or (_env.get(arm.api_key_env or "") or "")
        if not key or len(key) < 20:
            return None
        return DeepSeekAdapter(arm.model, key, arm.base_url or "https://api.deepseek.com")  # type: ignore[return-value]
    try:
        return get_llm_client(arm.provider, arm.model)
    except Exception:
        return None


def _summary_words(summary: str) -> int:
    return len(re.findall(r"\b\w+\b", summary))


def _skills_category_ok(skills: list[str]) -> bool:
    if not skills:
        return False
    return sum(1 for s in skills if ":" in s) >= max(1, len(skills) // 2)


def _keyword_hits(text: str, terms: list[str]) -> int:
    lower = text.lower()
    return sum(1 for t in terms if t.lower() in lower)


@dataclass
class ObjectiveScores:
    ats_score: int
    missing_keywords: int
    summary_words: int
    skills_category_format_ok: bool
    must_have_keyword_hits: int
    experience_bullet_count: int
    cover_letter_words: int
    cover_letter_in_range: bool
    estimated_phase3_cost_usd: float
    estimated_cover_cost_usd: float


async def _judge_rewrite(
    judge: LLMClient,
    *,
    case: dict,
    model_label: str,
    summary: str,
    experience_bullets: list[str],
) -> dict[str, float]:
    from pydantic import BaseModel, Field

    class JudgeScoresModel(BaseModel):
        jd_alignment: float = Field(ge=1, le=5)
        factual_fidelity: float = Field(ge=1, le=5)
        writing_quality: float = Field(ge=1, le=5)
        ats_readiness: float = Field(ge=1, le=5)
        notes: str = ""

    prompt = (
        f"You are evaluating a tailored resume rewrite for blind model '{model_label}'.\n"
        f"TARGET ROLE: {case['target_role']}\n"
        f"MUST-HAVE KEYWORDS: {', '.join(case['must_have'])}\n\n"
        f"ORIGINAL RESUME:\n{case['resume']}\n\n"
        f"JOB DESCRIPTION:\n{case['jd']}\n\n"
        f"REWRITE SUMMARY:\n{summary}\n\n"
        f"REWRITE EXPERIENCE BULLETS:\n" + "\n".join(f"- {b}" for b in experience_bullets[:12]) + "\n\n"
        "Score 1-5 (5 best). Penalize invented employers, titles, dates, or metrics. "
        "Reward exact JD keyword usage and strong bullets without fabrication."
    )
    result = await complete_structured(
        judge,
        [LLMMessage(role="user", content=prompt)],
        JudgeScoresModel,
        max_tokens=800,
    )
    return {
        "jd_alignment": result.jd_alignment,
        "factual_fidelity": result.factual_fidelity,
        "writing_quality": result.writing_quality,
        "ats_readiness": result.ats_readiness,
        "notes": result.notes,
    }


def _phase3_usable(tailored) -> bool:
    """Eval-only gate: accept strong summary even when postprocess drops bullets."""
    bullets = [b for exp in tailored.experience for b in exp.bullets if b.strip()]
    summary_ok = len(tailored.summary.strip()) >= 80
    skills_ok = len(tailored.skills) >= 2
    bullets_ok = len(bullets) >= 3
    return summary_ok or (bullets_ok and skills_ok)


async def _noop_company_intel(session) -> None:
    return None


async def _run_phase3_with_quality_gate(
    session: Session,
    client: LLMClient,
    queue: asyncio.Queue,
    *,
    max_attempts: int = 3,
):
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            tailored = await phase3_rewrite.run(session, client, queue)
        except Exception as exc:
            last_exc = exc
            continue
        bullets = [b for exp in tailored.experience for b in exp.bullets]
        if _phase3_usable(tailored):
            return tailored
        last_exc = RuntimeError(
            f"hollow phase3 (attempt {attempt + 1}): "
            f"summary_chars={len(tailored.summary.strip())} bullets={len(bullets)} skills={len(tailored.skills)}"
        )
    raise last_exc or RuntimeError("phase3 failed")


def _deepseek_cost_usd(input_tokens: int, output_tokens: int) -> float:
    # Off-peak V4-Flash public rates (Aug 2026)
    return round((input_tokens / 1_000_000) * 0.22 + (output_tokens / 1_000_000) * 0.66, 6)


async def _run_arm(case: dict, arm: ModelArm, judge: LLMClient) -> dict | None:
    client = _resolve_client(arm)
    if client is None:
        return {"arm": arm.label, "skipped": True, "reason": "no API key or model unavailable"}

    session = _build_session(case)
    queue: asyncio.Queue = asyncio.Queue()

    phase3_rewrite.ensure_session_company_intel = _noop_company_intel  # type: ignore[method-assign]

    try:
        tailored = await _run_phase3_with_quality_gate(session, client, queue)
    except Exception as exc:
        return {"arm": arm.label, "error": f"phase3: {type(exc).__name__}: {exc}"}

    session.phase3_output = tailored
    session.phase3_status = PhaseStatus.done

    try:
        cover = await cover_letter_agent.run(session, client, queue, tone="balanced")
    except Exception as exc:
        return {"arm": arm.label, "error": f"cover_letter: {type(exc).__name__}: {exc}"}

    must_terms = case["must_have"]
    score = compute_score_result(tailored, must_terms, career_stage=case["career_stage"])
    flat_text = json.dumps(tailored.model_dump())
    bullets = [b for exp in tailored.experience for b in exp.bullets]

    obj = ObjectiveScores(
        ats_score=score.ats_score,
        missing_keywords=len(score.missing_keywords),
        summary_words=_summary_words(tailored.summary),
        skills_category_format_ok=_skills_category_ok(tailored.skills),
        must_have_keyword_hits=_keyword_hits(flat_text, must_terms),
        experience_bullet_count=len(bullets),
        cover_letter_words=cover.word_count or _summary_words(cover.body_plain),
        cover_letter_in_range=250 <= (cover.word_count or 0) <= 420,
        estimated_phase3_cost_usd=(
            _deepseek_cost_usd(8000, 2500)
            if client.provider_name == "deepseek"
            else estimate_cost(8000, 2500, client.provider_name, client.model_name)
        ),
        estimated_cover_cost_usd=(
            _deepseek_cost_usd(6000, 900)
            if client.provider_name == "deepseek"
            else estimate_cost(6000, 900, client.provider_name, client.model_name)
        ),
    )

    judge_scores = await _judge_rewrite(
        judge,
        case=case,
        model_label=arm.label,
        summary=tailored.summary,
        experience_bullets=bullets,
    )

    return {
        "arm": arm.label,
        "provider": client.provider_name,
        "model": client.model_name,
        "objective": asdict(obj),
        "judge": judge_scores,
        "samples": {
            "summary": tailored.summary[:400],
            "skills": tailored.skills[:4],
            "top_bullets": bullets[:3],
            "cover_opening": cover.body_plain[:300],
        },
    }


async def main() -> None:
    _load_keys()
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("WARNING: DEEPSEEK_API_KEY not found in backend/.env — DeepSeek arm will be skipped.", flush=True)
    judge = get_llm_client(*JUDGE_MODEL)
    results = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "judge_model": f"{JUDGE_MODEL[0]}/{JUDGE_MODEL[1]}",
        "note": (
            "Uses gemini-3.5-* because gemini-2.5-* returns 404 on current API key. "
            "Production registry still pins 2.5 — migrate separately."
        ),
        "cases": [],
    }

    for case in EVAL_CASES:
        case_result = {"case_id": case["id"], "arms": []}
        print(f"\n=== Case: {case['id']} ===", flush=True)
        for arm in MODEL_ARMS:
            print(f"  Running {arm.label}...", flush=True)
            arm_result = await _run_arm(case, arm, judge)
            case_result["arms"].append(arm_result)
            if arm_result and not arm_result.get("skipped") and not arm_result.get("error"):
                j = arm_result["judge"]
                o = arm_result["objective"]
                avg = (j["jd_alignment"] + j["factual_fidelity"] + j["writing_quality"] + j["ats_readiness"]) / 4
                print(
                    f"    ATS={o['ats_score']} judge_avg={avg:.2f} "
                    f"missing_kw={o['missing_keywords']} cover_words={o['cover_letter_words']}",
                    flush=True,
                )
            elif arm_result and arm_result.get("skipped"):
                print(f"    SKIPPED: {arm_result.get('reason')}", flush=True)
            else:
                print(f"    ERROR: {arm_result}", flush=True)
        results["cases"].append(case_result)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "model_quality_latest.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}", flush=True)

    # Console summary table
    print("\n--- SUMMARY ---")
    for case in results["cases"]:
        print(f"\n{case['case_id']}:")
        rows = []
        for arm in case["arms"]:
            if not arm or arm.get("skipped") or arm.get("error"):
                label = arm.get("arm", "?") if arm else "?"
                rows.append((label, "SKIP/ERR", "-", "-", "-"))
                continue
            j = arm["judge"]
            o = arm["objective"]
            avg = (j["jd_alignment"] + j["factual_fidelity"] + j["writing_quality"] + j["ats_readiness"]) / 4
            rows.append(
                (
                    arm["arm"],
                    f"{avg:.2f}",
                    str(o["ats_score"]),
                    str(o["missing_keywords"]),
                    f"{o['estimated_phase3_cost_usd']*100:.2f}¢",
                )
            )
        print(f"{'Model':<22} {'Judge':>6} {'ATS':>4} {'MissKW':>6} {'P3cost':>8}")
        for row in rows:
            print(f"{row[0]:<22} {row[1]:>6} {row[2]:>4} {row[3]:>6} {row[4]:>8}")


if __name__ == "__main__":
    asyncio.run(main())
