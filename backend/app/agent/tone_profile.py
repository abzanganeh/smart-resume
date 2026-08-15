"""Deterministic JD tone / voice profile extractor.

Feeds Phase 3 prompt (voice-matching) and Phase 4 tone-alignment axis. Kept
purely deterministic so the same JD always produces the same profile — LLMs
must not influence the tonal signals we use to score.

Not a replacement for the Phase 1 LLM extraction; a complement that captures
stylistic features the keyword pipeline discards (formality, dominant verbs,
repeated multi-word phrases, sentence rhythm, industry register).
"""

from __future__ import annotations

import re
from collections import Counter
from enum import Enum
from statistics import median

from pydantic import BaseModel, Field

_MAX_DOMINANT_VERBS = 12
_MAX_DISTINCTIVE_PHRASES = 8
_MIN_PHRASE_WORDS = 2
_MAX_PHRASE_WORDS = 4
_MIN_PHRASE_LEN = 4  # short function words filtered
_MIN_PHRASE_FREQ = 2


class Formality(str, Enum):
    casual = "casual"
    neutral = "neutral"
    formal = "formal"
    executive = "executive"


class ReadingLevel(str, Enum):
    plain = "plain"
    professional = "professional"
    dense = "dense"


class JDToneProfile(BaseModel):
    """Stylistic fingerprint of a job description.

    Every field is populated by ``extract_tone_profile`` in a deterministic way
    so unit tests can pin behaviour and Phase 4's tone-alignment axis stays
    reproducible.
    """

    formality: Formality = Formality.neutral
    industry_register: str = "general"
    dominant_verbs: list[str] = Field(default_factory=list)
    distinctive_phrases: list[str] = Field(default_factory=list)
    sentence_length_median: int = 0
    reading_level: ReadingLevel = ReadingLevel.professional


_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "but", "of", "in", "on", "at", "to",
        "for", "with", "by", "as", "is", "are", "was", "were", "be", "been",
        "being", "this", "that", "these", "those", "we", "you", "your",
        "our", "us", "it", "its", "will", "can", "could", "should", "would",
        "have", "has", "had", "do", "does", "did", "not", "no", "yes",
        "who", "what", "when", "where", "why", "how", "which", "if", "so",
        "than", "then", "into", "from", "about", "over", "under", "up",
        "down", "out", "off", "against", "between", "some", "any", "all",
        "each", "every", "other", "such", "only", "own", "same", "very",
        "more", "most", "less", "least", "much", "many", "few",
    }
)

# Executive / formal register markers — verbs and nominalizations that
# dominate senior/executive JDs.
_EXECUTIVE_MARKERS = frozenset(
    {
        "architect", "orchestrate", "champion", "govern", "establish",
        "spearhead", "steward", "drive", "shape", "influence",
        "transform", "transformation", "enterprise", "executive",
        "stakeholder", "governance", "strategy", "strategic",
        "operational", "excellence", "c-suite", "board", "director",
        "vp", "vice", "president", "chief", "regulated", "compliance",
        "rigorous", "mastery", "seasoned", "progressive",
    }
)

_FORMAL_MARKERS = frozenset(
    {
        "responsibility", "responsibilities", "qualifications",
        "candidate", "successful", "seeking", "demonstrate",
        "demonstrated", "proven", "expertise", "collaborate",
        "collaboration", "leverage", "framework", "frameworks",
        "methodology", "methodologies", "initiative", "initiatives",
    }
)

_CASUAL_MARKERS = frozenset(
    {
        "we're", "we'll", "you'll", "you're", "let's", "stuff", "help",
        "jump", "hey", "cool", "fun", "growing", "tight-knit", "iterate",
        "ship", "hack", "vibe", "startup", "team", "chat", "grab", "kick",
    }
)

# Industry register buckets — matched against JD tokens.
_REGISTER_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "financial services",
        re.compile(
            r"\b(finance|financial|banking|insurance|regulated|compliance|"
            r"risk|audit|sox|gaap|hedge|treasury|capital|invest(?:or|ment)s?)\b",
            re.I,
        ),
    ),
    (
        "healthcare",
        re.compile(
            r"\b(healthcare|clinical|patient|hipaa|medical|pharmac|hospital|"
            r"provider|payer|ehr|emr)\b",
            re.I,
        ),
    ),
    (
        "e-commerce / retail",
        re.compile(r"\b(retail|e-?commerce|checkout|storefront|merchant|shopper)\b", re.I),
    ),
    (
        "government / public sector",
        re.compile(r"\b(government|federal|agency|public\s+sector|contractor)\b", re.I),
    ),
    (
        "AI / ML",
        re.compile(
            r"\b(machine\s+learning|deep\s+learning|neural|llm|generative|"
            r"foundation\s+model|nlp|computer\s+vision|mlops)\b",
            re.I,
        ),
    ),
    (
        "developer tools / SaaS",
        re.compile(
            r"\b(saas|developer\s+tools|api|sdk|platform|integration|open\s+source)\b",
            re.I,
        ),
    ),
    (
        "cybersecurity",
        re.compile(r"\b(security|cyber|zero\s*trust|threat|siem|soc|firewall|iam)\b", re.I),
    ),
]


def _tokenize_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z'-]{1,}", text.lower())


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}|\r\n{2,}", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _dominant_verbs(text: str) -> list[str]:
    """Return the JD's most-used action verbs, verbatim, ranked by frequency.

    Uses a conservative candidate set: words that (a) appear more than once,
    (b) are not stopwords, (c) look like verbs — either present-tense action
    verbs from a small closed list, or bullet-leading capitalized words.
    """
    tokens = _tokenize_words(text)
    if not tokens:
        return []

    counts: Counter[str] = Counter(t for t in tokens if t not in _STOPWORDS and len(t) >= 3)

    # Bullet-leading verbs (lines that begin with a capitalized action word)
    # get a small frequency boost so they dominate the list — these are the
    # verbs recruiters expect to see mirrored in bullets.
    bullet_lead_boost = 3
    for line in text.splitlines():
        stripped = line.strip().lstrip("-•*0123456789.)").strip()
        if not stripped:
            continue
        head = re.split(r"[\s,.:;]", stripped, maxsplit=1)[0]
        if head and head[:1].isupper() and head.isalpha() and len(head) > 2:
            counts[head.lower()] += bullet_lead_boost

    # Reject nouns / non-verb-ish tokens by requiring either bullet-lead
    # presence OR membership in a broad known-verb suffix pattern.
    verb_like: list[tuple[str, int]] = []
    for word, freq in counts.most_common():
        if freq < 1:
            continue
        if word in _STOPWORDS:
            continue
        # Simple heuristic: verbs used in JD imperatives tend to be short,
        # end in a variety of ways, and appear near the start of bullets.
        if _looks_like_verb(word):
            verb_like.append((word, freq))
        if len(verb_like) >= _MAX_DOMINANT_VERBS * 2:
            break

    verb_like.sort(key=lambda kv: (-kv[1], kv[0]))
    seen: set[str] = set()
    out: list[str] = []
    for word, _ in verb_like:
        if word in seen:
            continue
        seen.add(word)
        out.append(word)
        if len(out) >= _MAX_DOMINANT_VERBS:
            break
    return out


_VERB_ENDINGS = ("e", "d", "ed", "ing", "ate", "ify", "ize", "ise", "en", "er")
_KNOWN_VERBS = frozenset(
    {
        "architect", "orchestrate", "champion", "govern", "establish",
        "spearhead", "steward", "drive", "shape", "influence", "lead",
        "build", "ship", "deliver", "own", "design", "develop", "deploy",
        "improve", "reduce", "increase", "scale", "launch", "manage",
        "mentor", "coach", "collaborate", "partner", "align", "unify",
        "transform", "modernize", "automate", "streamline", "optimize",
        "orchestrate", "operate", "run", "support", "maintain", "monitor",
        "measure", "track", "analyze", "evaluate", "assess", "audit",
        "review", "test", "validate", "verify", "debug", "fix", "resolve",
        "troubleshoot", "diagnose", "investigate", "identify", "define",
        "document", "communicate", "present", "report", "advise",
        "recommend", "propose", "implement", "execute", "plan", "prioritize",
        "roadmap", "iterate", "pair", "help", "jump", "grow", "hire",
        "onboard", "coach", "guide", "teach", "train", "champion",
        "advocate", "negotiate", "sell", "close", "engage", "acquire",
    }
)


def _looks_like_verb(word: str) -> bool:
    if word in _KNOWN_VERBS:
        return True
    if any(word.endswith(suf) for suf in _VERB_ENDINGS):
        return True
    return False


def _distinctive_phrases(text: str) -> list[str]:
    """Repeated multi-word phrases (2–4 words) that likely carry the JD's flavor."""
    tokens = _tokenize_words(text)
    if len(tokens) < _MIN_PHRASE_WORDS * 2:
        return []

    filtered = [t for t in tokens if len(t) >= _MIN_PHRASE_LEN and t not in _STOPWORDS]
    counts: Counter[tuple[str, ...]] = Counter()
    for n in range(_MIN_PHRASE_WORDS, _MAX_PHRASE_WORDS + 1):
        for i in range(len(filtered) - n + 1):
            ngram = tuple(filtered[i : i + n])
            if all(len(t) >= 3 for t in ngram):
                counts[ngram] += 1

    # Rank by (frequency desc, ngram length desc) so longer repeated phrases
    # win when frequency ties, and drop hapaxes.
    ranked = sorted(
        (ng for ng, c in counts.items() if c >= _MIN_PHRASE_FREQ),
        key=lambda ng: (-counts[ng], -len(ng), ng),
    )
    seen_supersets: list[tuple[str, ...]] = []
    out: list[str] = []
    for ng in ranked:
        # Skip phrases that are strict substrings of an already-included phrase
        # to avoid noise like ["quality engineering", "quality"] both landing.
        joined = " ".join(ng)
        if any(joined in " ".join(s) and ng != s for s in seen_supersets):
            continue
        out.append(joined)
        seen_supersets.append(ng)
        if len(out) >= _MAX_DISTINCTIVE_PHRASES:
            break
    return out


def _formality(text: str, tokens: set[str]) -> Formality:
    exec_hits = sum(1 for t in tokens if t in _EXECUTIVE_MARKERS)
    formal_hits = sum(1 for t in tokens if t in _FORMAL_MARKERS)
    casual_hits = sum(1 for t in tokens if t in _CASUAL_MARKERS)
    lower = text.lower()
    if re.search(r"\byou'?ll\b|\bwe'?ll\b|\bwe'?re\b|\byou'?re\b", lower):
        casual_hits += 2

    if exec_hits >= 3 and exec_hits > casual_hits:
        return Formality.executive
    if formal_hits >= 3 and formal_hits > casual_hits:
        return Formality.formal
    if casual_hits >= 3 and casual_hits > (exec_hits + formal_hits):
        return Formality.casual
    return Formality.neutral


def _reading_level(sentences: list[str], formality: Formality) -> ReadingLevel:
    """Reading level factors in prose density AND formality.

    Bullet-heavy JDs pull the median sentence length down even when the
    surrounding prose is dense; formality lets us keep those in the
    ``professional`` bucket rather than mislabeling them as ``plain``.
    """
    if not sentences:
        return ReadingLevel.professional

    # Consider prose only — bullets and short fragments drag the median down.
    prose_lengths = [
        len(_tokenize_words(s))
        for s in sentences
        if s.strip() and not s.lstrip().startswith(("-", "•", "*"))
        and len(_tokenize_words(s)) >= 6
    ]
    prose_med = int(median(prose_lengths)) if prose_lengths else 0

    if formality == Formality.executive or prose_med >= 22:
        return ReadingLevel.dense
    if formality == Formality.formal or prose_med >= 14:
        return ReadingLevel.professional
    if prose_med <= 10:
        return ReadingLevel.plain
    return ReadingLevel.professional


def _median_sentence_length(sentences: list[str]) -> int:
    if not sentences:
        return 0
    lengths = [len(_tokenize_words(s)) for s in sentences if s.strip()]
    if not lengths:
        return 0
    return int(median(lengths))


def _industry_register(text: str) -> str:
    hits: Counter[str] = Counter()
    for label, pattern in _REGISTER_RULES:
        matches = pattern.findall(text)
        if matches:
            hits[label] = len(matches)
    if not hits:
        # Fall back to a generic label based on presence of dev vocabulary.
        if re.search(r"\b(software|engineer|developer|code|repository)\b", text, re.I):
            return "technology"
        return "general"
    return hits.most_common(1)[0][0]


def extract_tone_profile(jd_text: str) -> JDToneProfile:
    """Return a deterministic tone/voice profile for ``jd_text``.

    Empty / near-empty input yields a neutral profile so downstream code can
    safely treat this as "no signal" without special-casing.
    """
    if not jd_text or not jd_text.strip():
        return JDToneProfile()

    sentences = _sentences(jd_text)
    tokens = set(_tokenize_words(jd_text))
    formality = _formality(jd_text, tokens)

    return JDToneProfile(
        formality=formality,
        industry_register=_industry_register(jd_text),
        dominant_verbs=_dominant_verbs(jd_text),
        distinctive_phrases=_distinctive_phrases(jd_text),
        sentence_length_median=_median_sentence_length(sentences),
        reading_level=_reading_level(sentences, formality),
    )


__all__ = [
    "Formality",
    "JDToneProfile",
    "ReadingLevel",
    "extract_tone_profile",
]
