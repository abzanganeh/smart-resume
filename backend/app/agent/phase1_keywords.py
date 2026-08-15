from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import structlog
from pydantic import BaseModel

from app.agent.tone_profile import extract_tone_profile
from app.llm.base import LLMClient, LLMMessage
from app.llm.context import truncate_to_fit
from app.llm.structured import complete_structured
from app.models.keywords import Keyword, KeywordExtractionOutput, KeywordStringsOutput
from app.models.session import Session

log = structlog.get_logger()

_SYSTEM_BASE = (Path(__file__).parent / "prompts" / "system_base.txt").read_text()
_PHASE1 = (Path(__file__).parent / "prompts" / "phase1.txt").read_text()

_FALLBACK_SYSTEM = (
    "Extract ATS keywords from the job description. "
    "Return JSON with must_have_keywords and nice_to_have_keywords as arrays of exact JD phrases."
)


def _phase1_is_hollow(output: KeywordExtractionOutput) -> bool:
    return not output.must_have_keywords and not output.nice_to_have_keywords


def _reject_hollow_phase1(output: BaseModel) -> str | None:
    if isinstance(output, KeywordExtractionOutput) and _phase1_is_hollow(output):
        return (
            "Response is empty. Extract at least 3 must_have_keywords from required qualifications "
            "and 1+ nice_to_have_keywords. Each keyword needs term, source_sentence, category, tier, reason."
        )
    return None


def _source_sentence_for_term(term: str, jd_text: str) -> str:
    term_lower = term.lower()
    for line in jd_text.splitlines():
        stripped = line.strip()
        if stripped and term_lower in stripped.lower():
            return stripped[:240]
    for sentence in re.split(r"[.!?]\s+", jd_text):
        if term_lower in sentence.lower():
            return sentence.strip()[:240]
    return jd_text.strip()[:240]


def _infer_category(term: str) -> str:
    t = term.lower()
    if any(x in t for x in ("python", "java", "go", "rust", "c++", "typescript", "javascript")):
        return "language"
    if any(x in t for x in ("kubernetes", "docker", "aws", "gcp", "azure", "linux")):
        return "tool"
    if any(x in t for x in ("machine learning", "deep learning", "nlp", "llm")):
        return "domain"
    return "tool"


def _strings_to_keywords(
    terms: list[str],
    tier: str,
    jd_text: str,
    resume_lower: str,
) -> list[Keyword]:
    keywords: list[Keyword] = []
    seen: set[str] = set()
    for term in terms:
        cleaned = term.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(
            Keyword(
                term=cleaned,
                source_sentence=_source_sentence_for_term(cleaned, jd_text),
                category=_infer_category(cleaned),  # type: ignore[arg-type]
                tier=tier,  # type: ignore[arg-type]
                reason="Extracted from job description",
                present_in_resume=key in resume_lower or cleaned.lower() in resume_lower,
            )
        )
    return keywords


def _heuristic_keywords_from_jd(jd_text: str, resume_lower: str) -> KeywordExtractionOutput:
    """Last-resort extraction when the LLM returns empty output."""
    must_terms: list[str] = []
    nice_terms: list[str] = []

    for line in jd_text.splitlines():
        stripped = line.strip().lstrip("-•*").strip()
        if not stripped or len(stripped) < 4:
            continue
        lower = stripped.lower()
        if any(m in lower for m in ("required", "must have", "must-have", "minimum qualifications")):
            must_terms.append(stripped[:120])
        elif any(m in lower for m in ("preferred", "nice to have", "bonus", "plus")):
            nice_terms.append(stripped[:120])

    # Common tech tokens in JD
    tech_pattern = re.compile(
        r"\b(Python|Java|Go|Rust|Kubernetes|Docker|AWS|GCP|Azure|Linux|CUDA|PyTorch|"
        r"TensorFlow|SQL|PostgreSQL|Redis|Kafka|gRPC|distributed systems|machine learning|"
        r"LLM|GPU|C\+\+|TypeScript|JavaScript)\b",
        re.I,
    )
    for match in tech_pattern.finditer(jd_text):
        term = match.group(0)
        if term.lower() not in {t.lower() for t in must_terms + nice_terms}:
            must_terms.append(term)

    must_kw = _strings_to_keywords(must_terms[:12], "must_have", jd_text, resume_lower)
    nice_kw = _strings_to_keywords(nice_terms[:8], "nice_to_have", jd_text, resume_lower)

    if not must_kw and not nice_kw:
        must_kw = _strings_to_keywords(["See job description"], "must_have", jd_text, resume_lower)

    return KeywordExtractionOutput(
        must_have_keywords=must_kw,
        nice_to_have_keywords=nice_kw,
        boolean_search_terms=[k.term for k in must_kw[:10]],
    )


async def _fallback_keyword_extraction(
    llm: LLMClient,
    jd_text: str,
    resume_text: str,
) -> KeywordExtractionOutput:
    messages = [
        LLMMessage(role="system", content=_FALLBACK_SYSTEM),
        LLMMessage(
            role="user",
            content=(
                f"JOB DESCRIPTION:\n{jd_text}\n\n"
                "Return JSON with must_have_keywords (array of exact phrases) and "
                "nice_to_have_keywords (array of exact phrases). Include at least 3 must-haves."
            ),
        ),
    ]
    try:
        parsed = await complete_structured(
            llm, messages, KeywordStringsOutput, max_tokens=4096, max_retries=3,
        )
        resume_lower = resume_text.lower()
        must_kw = _strings_to_keywords(parsed.must_have_keywords, "must_have", jd_text, resume_lower)
        nice_kw = _strings_to_keywords(parsed.nice_to_have_keywords, "nice_to_have", jd_text, resume_lower)
        if must_kw or nice_kw:
            return KeywordExtractionOutput(
                must_have_keywords=must_kw,
                nice_to_have_keywords=nice_kw,
                action_verbs=parsed.action_verbs,
                seniority_signals=parsed.seniority_signals,
                boolean_search_terms=[k.term for k in must_kw],
            )
    except Exception as exc:
        log.warning("phase1_fallback_llm_failed", error=str(exc))

    return _heuristic_keywords_from_jd(jd_text, resume_text.lower())


async def run(
    session: Session,
    llm: LLMClient,
    event_queue: asyncio.Queue,
) -> KeywordExtractionOutput:
    await event_queue.put({"event": "progress", "phase": 1, "message": "Analyzing job description…"})

    from app.parsers.html_parser import strip_html_to_text

    resume_text = session.resume_raw or ""
    # Strip HTML from jd_raw in case the URL fetcher stored raw HTML
    # (e.g. Jobright, Greenhouse, or other JS-rendered job boards).
    raw_jd = session.jd_raw or ""
    jd_text = strip_html_to_text(raw_jd)

    if not jd_text.strip():
        raise RuntimeError("Job description is empty.")

    # Guard against JS-rendered pages that return a thin HTML shell with
    # no readable text (Jobright, Greenhouse, Lever, etc.). Fewer than 200
    # characters after stripping is a strong signal the scraper got nothing
    # useful — refusing here prevents the LLM from hallucinating keywords
    # from the resume when there is no JD content to work with.
    MIN_JD_CHARS = 200
    if len(jd_text.strip()) < MIN_JD_CHARS:
        raise RuntimeError(
            "The job description URL returned a page-loading shell with no readable text "
            "(the site uses JavaScript rendering). "
            "Please paste the job description text directly into the JD field."
        )

    resume_text, jd_text = truncate_to_fit(llm, resume_text, jd_text)

    messages = [
        LLMMessage(role="system", content=_SYSTEM_BASE + "\n\n" + _PHASE1),
        LLMMessage(
            role="user",
            content=(
                f"JOB DESCRIPTION:\n{jd_text}\n\n"
                f"CANDIDATE'S CURRENT RESUME (for keyword presence check):\n{resume_text}"
            ),
        ),
    ]

    await event_queue.put({"event": "progress", "phase": 1, "message": "Identifying must-have vs. nice-to-have keywords…"})
    await event_queue.put({"event": "progress", "phase": 1, "message": "Checking which keywords are already in your resume…"})

    output: KeywordExtractionOutput | None = None
    try:
        output = await complete_structured(
            llm,
            messages,
            KeywordExtractionOutput,
            max_tokens=8192,
            max_retries=5,
            accept_result=_reject_hollow_phase1,
        )
    except Exception as exc:
        log.warning("phase1_structured_failed", error=str(exc))
        output = None

    if output is None or _phase1_is_hollow(output):
        log.warning("phase1_using_fallback_extractor")
        await event_queue.put({"event": "progress", "phase": 1, "message": "Retrying keyword extraction with simplified prompt…"})
        output = await _fallback_keyword_extraction(llm, jd_text, resume_text)

    # Supplement LLM's present_in_resume with smarter heuristic matching.
    resume_lower = resume_text.lower()
    dehyphen = resume_lower.replace("-", " ")

    _QUALIFIERS = re.compile(
        r"^(?:proficient\s+in|experience\s+(?:in|with|designing(?:\s+and\s+developing)?)?|"
        r"experienced?\s+(?:in|with)|knowledge\s+of|familiarity\s+with|skilled\s+in|"
        r"expertise\s+in|strong\s+background\s+in|ability\s+to|"
        r"\d+\+\s*years?\s+(?:of\s+)?(?:working\s+)?)\s*",
        re.I,
    )
    _STOPWORDS = frozenset(
        {"in", "with", "of", "and", "the", "a", "an", "for", "to", "on", "at",
         "by", "such", "as", "is", "are", "be", "via", "using", "including"}
    )
    _ABBREV = {
        "oo ": "object-oriented ",
        "oop": "object-oriented programming",
        "ml": "machine learning",
        "ai": "artificial intelligence",
        "aws": "amazon aws",
    }

    def _string_present(term: str) -> bool:
        t = term.lower()
        if t in dehyphen:
            return True
        if re.match(r"^\d+\+?\s+years?\s+", t, re.I):
            return False

        def _try_abbrev(s: str) -> bool:
            for abbrev, full in _ABBREV.items():
                key = abbrev.strip()
                if re.search(r"\b" + re.escape(key) + r"\b", s):
                    candidate = re.sub(r"\s+", " ",
                                       re.sub(r"\b" + re.escape(key) + r"\b", full.strip(), s)).strip()
                    if candidate in dehyphen:
                        return True
            return False

        if _try_abbrev(t):
            return True

        core = _QUALIFIERS.sub("", t).strip()
        if core and core != t and core in dehyphen:
            return True
        if core and _try_abbrev(core):
            return True

        words = [w for w in re.split(r"\W+", core or t) if len(w) > 2 and w not in _STOPWORDS]
        if len(words) >= 2 and all(w in dehyphen for w in words):
            return True
        if len(words) == 1 and words[0] in dehyphen:
            return True
        return False

    for kw in output.must_have_keywords + output.nice_to_have_keywords:
        if _string_present(kw.term):
            kw.present_in_resume = True

    # Deterministic tone profile (§Track A). LLM output cannot override this —
    # the profile is a stylistic fingerprint used by Phase 3 wording guidance
    # and Phase 4's tone-alignment axis.
    output.tone_profile = extract_tone_profile(jd_text)

    await event_queue.put({"event": "partial", "phase": 1, "data": json.loads(output.model_dump_json())})
    log.info(
        "phase1_done",
        must_have=len(output.must_have_keywords),
        nice_to_have=len(output.nice_to_have_keywords),
        tone_formality=output.tone_profile.formality.value,
        tone_register=output.tone_profile.industry_register,
    )
    return output
