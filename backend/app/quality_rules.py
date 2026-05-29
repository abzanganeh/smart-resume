"""
Resume quality rules — encoded from resume-quality-rules.md.
These constants are injected into agent prompts via system_base.txt.
"""

BULLET_RULES = """
BULLET WRITING RULES:
- Begin every bullet with a strong action verb: Built, Led, Deployed, Reduced, Improved, Automated, Scaled, Architected, Launched, Drove...
- Quantify impact — use numbers, percentages, dollar amounts, or scale. No vague claims.
- No clichés: remove "team player", "results-driven", "passionate about", "detail-oriented", "hard worker".
- Cut anything irrelevant to the target role, regardless of how impressive it sounds.
- Use recruiter-friendly language: avoid internal jargon, acronyms not in the JD, obscure job titles.
"""

ATS_RULES = """
ATS & KEYWORD RULES:
- Use EXACT phrasing from the job description — ATS systems match literally, not semantically.
- Keyword placement priority: Skills section (list) → Experience bullets (integrated) → Summary (2-3 core terms).
- Target 5-8 must-have keywords. Every must-have keyword must appear verbatim at least once.
- Boolean recruiter searches use exact terms: (Python AND (C++ OR Java)) AND (infra OR infrastructure).
  If a term is not present verbatim, the candidate does not surface.
"""

TAILORING_RULES = """
TAILORING RULES:
- Never produce a generic resume. Every output is tailored to one specific JD.
- List skills in order of JD relevance, not alphabetically or chronologically.
- Mirror the JD's own vocabulary in bullet language.
- Professional contact details required: email must use full name, no nicknames.
- Never fabricate experience, metrics, or skills the user did not provide.
  If a metric is missing, flag it with a metrics_needed entry — do not invent a number.
"""

LENGTH_RULES = """
LENGTH RULES:
- Early / Mid career: 1 page maximum.
- Senior: 2 pages maximum. Never exceed 2 pages.
- Every line must earn its place. White noise buries the signal.
"""

TRANSITION_FRAMING = """
CAREER TRANSITION FRAMING (apply when CAREER TRANSITION = True):
- Lead with transferable skills most relevant to the target role.
- Add a Projects or Portfolio section if the candidate has relevant work to showcase.
- Include certifications and self-study that bridge the gap.
- Frame all prior work through a lens of relevance to the target role.
- Do not hide prior career — reframe it as complementary experience.
"""

QA_CHECKLIST = """
FINAL QA CHECKLIST — every output must pass all 8 items:
1. Tailored to one specific JD.
2. Top JD keywords present in Skills, Experience bullets, and Summary.
3. All bullets start with action verbs and include concrete metrics.
4. Language is recruiter-friendly (no internal jargon, clear outcomes).
5. Only relevant experience is included.
6. Resume is within page limits (1 page early/mid, 2 pages max senior).
7. Contact details are professional (especially email address).
8. If transitioning to ML: projects/coursework/stats signals are visible.
"""

ALL_RULES = "\n".join([BULLET_RULES, ATS_RULES, TAILORING_RULES, LENGTH_RULES, QA_CHECKLIST])
