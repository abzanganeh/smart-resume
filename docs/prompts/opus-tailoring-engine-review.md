# Opus Review Prompt — Job Tailoring Engine

Copy everything below the line into a new Opus chat. Attach or reference this repo (`smart-resume`), especially `backend/app/agent/` and `docs/fisher_investments_resume.pdf` as a JobRight-quality benchmark.

---

## Role

You are a senior staff engineer reviewing the **Smart Resume job tailoring engine** (Phases 1–4). Your goal is to find **logic gaps, prompt contradictions, and ATS-quality failures** that explain why tailored resumes score lower than JobRight-style outputs (~10/10 ATS) while preserving all **manual UI editing** flows unchanged.

## Hard constraints (do NOT recommend changing)

- **Do not change** the Tailored Editor manual-edit UX: inline edit, skills textarea, per-section Regenerate buttons, suggestion accept/reject, undo/redo, chat patches, version history UI.
- **Do not remove** user control over the final resume — improvements must come from **backend prompts, post-processing, phase orchestration, and QA logic**.
- **Do not fabricate** experience, metrics, titles, or companies — truthfulness rules stay.

## Benchmark

Compare engine behavior against:

1. **JobRight-style output** — see `docs/fisher_investments_resume.pdf` (user's Fisher Investments tailored resume, reported 10/10 ATS).
2. **User-reported failures**:
   - Skills still appear as a **flat chip list** instead of **categorized groups** (e.g. `AI & ML: Python, LLMs, RAG`).
   - Full regeneration **dropped accepted experience** entries that existed only in `phase3_output`, not in `resume_raw`.
   - ATS score drops from ~80 to ~65 after tailoring; suggestions sometimes worsen placement.
   - Regenerate Skills does not reliably add missing JD keywords or fix categorization.

## System map — review these files first

| Area | Path |
|------|------|
| Phase 3 rewrite + scoped regen | `backend/app/agent/phase3_rewrite.py` |
| Phase 3 post-process (deterministic) | `backend/app/agent/phase3_postprocess.py` |
| Phase 3 prompt | `backend/app/agent/prompts/phase3.txt` |
| Phase 4 QA / ATS scoring | `backend/app/agent/phase4_qa.py`, `prompts/phase4.txt` |
| Phase 1 keywords | `backend/app/agent/phase1_*.py`, `prompts/phase1.txt` |
| Phase 2 audit | `backend/app/agent/phase2_*.py`, `prompts/phase2.txt` |
| Orchestrator / phase locks | `backend/app/agent/orchestrator.py`, `routers/phases.py` |
| Export (PDF/DOCX/HTML skills layout) | `backend/app/services/export_service.py`, `templates/resume.html` |
| Quality rules | `.cursor/rules/resume-quality.mdc` |
| Frontend orchestration (read-only for context) | `frontend/app/session/[id]/page.tsx` — **do not propose UI edits to manual editor** |

## Review questions

Answer each with **file:line evidence**, severity (P0/P1/P2), and a **concrete fix** (prompt text, post-process rule, or orchestration change — not UI).

### A. Prompt consistency

1. Does `phase3.txt` **require** categorized skills while the JSON example or other sections still imply flat lists?
2. Are bullet-count rules (current job ≤5, prior ≤3, projects ≤2–3) stated clearly and enforced anywhere besides the LLM?
3. Does Phase 3 instruct **dual placement** of must-have keywords (Skills + Experience/Summary)? Does Phase 4 scoring align with that rule?
4. Do scoped regeneration instructions (`_scoped_user_instruction`) contradict the full-run prompt?

### B. Data flow & state

5. On **full Phase 3 re-run**, what inputs does the LLM see — `resume_raw` only, or also `phase3_output`? What gets lost (accepted suggestions, manual patches, added experience)?
6. When user **patches** tailored resume via API (`patchTailoredResume`), does the next scoped/full regen use the patched output?
7. Does `_merge_scoped_output` for skills **replace** or **append**? Can flat skills from LLM overwrite categorized skills?

### C. ATS quality vs JobRight

8. Compare Fisher/JobRight resume structure: summary length, skill grouping, keyword density, bullet concision, section order. What's missing in our Phase 3 output schema or prompts?
9. Why might Phase 4 **lower** ATS after a good Phase 2 audit? Check keyword detection in `_collect_resume_text`, false positives in blocking_issues, and score_ceiling logic.
10. Are Phase 4 suggestions ever telling users to "add to Skills" when keywords are already in Skills but missing from Experience?

### D. Deterministic enforcement

11. Is `postprocess_tailored_output` sufficient, or should categorization use JD keywords + master-resume skill chunks?
12. Should post-process run on **patch** responses too (when user saves skills manually as flat list)?
13. Are export formats (PDF/HTML/DOCX) rendering categorized skills correctly for ATS parsers?

### E. Retrieval & master resume

14. When `user_id` is set, does retrieval inject enough skill/experience context for categorization?
15. Do skipped chunks explain missing keywords in output?

## Deliverables

Produce a structured report:

```markdown
# Tailoring Engine Review

## Executive summary (5 bullets)

## P0 — Must fix before next release
- [ ] Issue …
  - Evidence: …
  - Fix: …

## P1 — High impact
…

## P2 — Nice to have
…

## JobRight parity checklist
| Capability | JobRight | Smart Resume | Gap |
|------------|----------|--------------|-----|
| Categorized skills | … | … | … |
| Keyword in 2+ sections | … | … | … |
| … | … | … | … |

## Recommended implementation order (max 8 steps, backend-only)

## Test plan
- Unit tests to add
- Integration scenarios (full regen, scoped skills regen, regen after accept suggestion)
```

## Implementation note for reviewer

If you implement fixes: work on branch `feat/tailoring-engine-improvements`. Commit backend/prompt changes only unless a bug is purely in phase orchestration on the frontend (no TailoredEditor UI changes).

---

*Generated for Smart Resume — tailoring engine audit.*
