"""Deterministic Phase 3 tone lint.

Reads the JD tone profile and the tailored resume output, appending
descriptive findings to ``rewrite_notes``. Never mutates bullets — repair
would just be fabrication pressure by another name (see grounding pattern
in the milestone task file).
"""

from __future__ import annotations

import re

from app.agent.tone_profile import Formality, JDToneProfile
from app.models.rewrite import TailoredResumeOutput

_CASUAL_HEDGE_VERBS = frozenset(
    {
        "worked", "helped", "assisted", "handled", "did", "jumped",
        "chipped", "pitched", "hopped", "poked",
    }
)

_STIFF_VERBS = frozenset(
    {
        "orchestrated", "architected", "championed", "spearheaded",
        "stewarded", "governed", "instituted", "operationalized",
        "reengineered", "consolidated", "harmonized",
    }
)

_MIN_VERB_REUSE_RATIO = 0.30  # 30% of bullets should reuse a JD verb


def _extract_first_verb(bullet: str) -> str:
    token = re.split(r"[\s,]", bullet.strip(), maxsplit=1)[0].strip()
    return token.lower().strip(".,;:")


def _bullets(output: TailoredResumeOutput) -> list[str]:
    bullets: list[str] = []
    for entry in output.experience:
        bullets.extend(b for b in entry.bullets if b.strip())
    for project in output.projects:
        if isinstance(project, dict):
            proj_bullets = project.get("bullets") or []
            if isinstance(proj_bullets, list):
                bullets.extend(b for b in proj_bullets if isinstance(b, str) and b.strip())
    return bullets


def _dominant_verb_reuse_ratio(bullets: list[str], dominant_verbs: list[str]) -> float:
    if not bullets or not dominant_verbs:
        return 0.0
    lowered = {v.lower().rstrip("es").rstrip("ed").rstrip("ing") for v in dominant_verbs if v}
    hits = 0
    for bullet in bullets:
        text = bullet.lower()
        if any(re.search(rf"\b{re.escape(stem)}\w*", text) for stem in lowered if stem):
            hits += 1
    return hits / len(bullets)


def _count_casual_hedges(bullets: list[str]) -> int:
    return sum(1 for b in bullets if _extract_first_verb(b) in _CASUAL_HEDGE_VERBS)


def _count_stiff_openers(bullets: list[str]) -> int:
    return sum(1 for b in bullets if _extract_first_verb(b) in _STIFF_VERBS)


def annotate_tone_alignment(
    output: TailoredResumeOutput,
    tone_profile: JDToneProfile,
) -> TailoredResumeOutput:
    """Append tone findings to ``rewrite_notes`` and return the output.

    Pure function; safe to call multiple times (findings are deduplicated
    against existing notes).
    """
    if tone_profile.formality == Formality.neutral and not tone_profile.dominant_verbs:
        return output

    bullets = _bullets(output)
    if not bullets:
        return output

    findings: list[str] = []
    reuse_ratio = _dominant_verb_reuse_ratio(bullets, tone_profile.dominant_verbs)

    if tone_profile.dominant_verbs and reuse_ratio < _MIN_VERB_REUSE_RATIO:
        findings.append(
            "Tone: only "
            f"{int(reuse_ratio * 100)}% of bullets reuse the JD's dominant verbs "
            f"({', '.join(tone_profile.dominant_verbs[:5])}). "
            "Consider rewriting a bullet to mirror the JD's action verbs where the "
            "candidate's real experience supports the action — this improves "
            "recruiter tonal recognition without changing the underlying facts."
        )

    casual_hedges = _count_casual_hedges(bullets)
    stiff_openers = _count_stiff_openers(bullets)

    if tone_profile.formality in {Formality.executive, Formality.formal} and casual_hedges >= 1:
        findings.append(
            "Tone: bullets open with casual verbs (e.g. worked/helped/assisted) but "
            f"the JD register is {tone_profile.formality.value}. Consider stronger "
            "leadership verbs from the tone profile if the candidate's real scope supports them."
        )
    if tone_profile.formality == Formality.casual and stiff_openers >= 2:
        findings.append(
            "Tone: bullets open with heavy corporate verbs but the JD register is casual. "
            "Consider a plainer verb set (build / ship / fix / own) to match the JD's voice."
        )

    if not findings:
        return output

    existing = {n.strip() for n in output.rewrite_notes}
    merged_notes = list(output.rewrite_notes)
    for finding in findings:
        if finding.strip() not in existing:
            merged_notes.append(finding)

    return output.model_copy(update={"rewrite_notes": merged_notes})


__all__ = ["annotate_tone_alignment"]
