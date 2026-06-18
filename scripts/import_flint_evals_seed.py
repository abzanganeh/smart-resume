#!/usr/bin/env python3
"""Import Flint evals/questions JSON packs into Smart Resume question seed bank."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

CANONICAL_BY_CATEGORY: dict[str, str] = {
    "introduction": (
        "Open with current role and scope, cite 2–3 relevant outcomes, "
        "then connect your trajectory to this role and team."
    ),
    "strengths": (
        "Name one strength, give a concrete STAR example with measurable impact, "
        "and tie it to a requirement from the job description."
    ),
    "weaknesses": (
        "Choose a real growth area, show deliberate improvement actions and results, "
        "and explain how you manage it in high-stakes work."
    ),
    "star_story": (
        "Use STAR: situation with stakes, your specific actions, trade-offs, "
        "and a quantified or qualitative outcome plus one lesson learned."
    ),
    "behavioural": (
        "Describe the situation briefly, your approach, collaboration choices, "
        "and a clear outcome that demonstrates mature professional judgment."
    ),
    "technical": (
        "Define terms precisely, explain trade-offs, walk through a concrete example "
        "from your experience, and state when you would choose an alternative."
    ),
    "system_design": (
        "Clarify requirements and scale, propose components and data flow, "
        "discuss bottlenecks and failure modes, then summarize trade-offs."
    ),
    "general": (
        "Prepare a personal answer grounded in your resume and this role's context."
    ),
}


def canonical_for(category: str) -> str:
    return CANONICAL_BY_CATEGORY.get(category.lower(), CANONICAL_BY_CATEGORY["general"])


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    flint_evals = Path(__file__).resolve().parents[2] / "Flint" / "evals" / "questions"
    if not flint_evals.is_dir():
        flint_evals = Path("/home/alireza/Desktop/projects/Flint/evals/questions")
    out_dir = repo_root / "backend" / "app" / "services" / "questions" / "seed"
    out_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    for src in sorted(flint_evals.glob("*.json")):
        payload = json.loads(src.read_text(encoding="utf-8"))
        questions = []
        for item in payload.get("questions", []):
            category = str(item.get("category") or "general")
            enriched = dict(item)
            if not enriched.get("canonical_answer"):
                enriched["canonical_answer"] = canonical_for(category)
            questions.append(enriched)
        payload["questions"] = questions
        payload["version"] = 2
        dest = out_dir / src.name
        dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        total += len(questions)
        print(f"wrote {dest.name}: {len(questions)} questions")

    print(f"total seed questions: {total}")


if __name__ == "__main__":
    main()
