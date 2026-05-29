# Smart Resume Agent — System Design

> AI-powered web app that tailors a resume to a specific job description using ATS keyword analysis and evidence-based quality rules.

This document describes the **current implementation** in the repo (as of May 2026). For setup instructions, see the root `README.md`.

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [Quality Rules](#2-quality-rules)
3. [User Journey](#3-user-journey)
4. [Architecture](#4-architecture)
5. [BYOK & LLM Providers](#5-byok--llm-providers)
6. [Agent Pipeline](#6-agent-pipeline)
7. [Frontend](#7-frontend)
8. [Backend & API](#8-backend--api)
9. [Data Models](#9-data-models)
10. [Session Store](#10-session-store)
11. [Export](#11-export)
12. [Configuration](#12-configuration)
13. [Technology Stack](#13-technology-stack)
14. [Repository Layout](#14-repository-layout)
15. [Security & Privacy](#15-security--privacy)
16. [Observability](#16-observability)
17. [Known Gaps & Future Work](#17-known-gaps--future-work)

---

## 1. Product Overview

### What it does

1. User picks an LLM provider and enters their API key (BYOK)
2. Uploads or pastes a resume (PDF, DOCX, or plain text)
3. Pastes a job description (optional URL fetch)
4. Fills in supplemental contact and career context
5. A four-phase agent extracts JD keywords, audits gaps, rewrites the resume, and runs a QA checklist
6. User reviews results, edits inline, and downloads PDF / DOCX / TXT

### What it is not

- Not a generic resume polisher — every run is tied to one JD
- Not template substitution — each phase uses structured LLM output with Pydantic validation
- Not a one-shot prompt — phases run sequentially with explicit inputs/outputs and quality gates

### Sessions

- Anonymous — no accounts
- **24-hour TTL** (`SESSION_TTL_SECONDS=86400`)
- Frontend shows a warning banner after **20 hours** (client-side timer)
- No cross-session history; users must download before expiry

---

## 2. Quality Rules

Rules live in `backend/app/quality_rules.py` and are injected into every agent call via `backend/app/agent/prompts/system_base.txt`. They mirror the private `resume/docs/resume-quality-rules.md` source.

| Area | Rule |
|---|---|
| Bullets | Strong action verb first; quantify impact; no clichés; cut irrelevant content |
| Length | Early/mid career → 1 page; senior → 2 pages max |
| ATS | Use **exact JD phrasing**; priority: Skills → Experience → Summary; target 5–8 must-have keywords |
| Tailoring | Skills ordered by JD relevance; mirror JD vocabulary; never fabricate metrics or experience |
| Career transition | When `is_career_transition=true`, reframe prior work and surface projects/certs (see `TRANSITION_FRAMING` in code) |
| QA | 8-point checklist in Phase 4; unresolved `metrics_needed` items fail QA |

---

## 3. User Journey

### Input wizard (`/session/new`)

Steps are driven by the `?step=` query param:

```
ai → resume → jd → info
```

| Step | Component | Action |
|---|---|---|
| `ai` | Provider setup | Pick provider + model; test key via `POST /api/llm/verify`; stored in `sessionStorage` |
| `resume` | `ResumeUploader` | Upload PDF/DOCX/TXT or paste text; LLM structures into `ParsedResume` |
| `jd` | `JDInput` | Paste JD or optional URL; saved to session |
| `info` | `UserInfoForm` | Contact, career stage, target role, certifications; creates session payload |

On completion → redirect to `/session/{id}?step=keywords`.

### Agent session (`/session/[id]`)

```
keywords → audit → rewrite → export
```

Each step maps to agent phase 1–4. Entering a step auto-triggers the phase (via `POST .../run` + SSE). Cached outputs replay without re-running unless the user clicks **Re-run**.

```
┌──────────────────────────────────────────────────────────────┐
│  WIZARD: ai → resume → jd → info                             │
└────────────────────────────┬─────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  Phase 1 — Keywords     SSE → KeywordDashboard               │
│  Phase 2 — Audit        SSE → AuditPanel (+ claimed keywords)│
│  Phase 3 — Rewrite      SSE → ResumeDiff / TailoredEditor    │
│  Phase 4 — QA           SSE → QAChecklist + ExportButtons    │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Architecture

```
Browser (Next.js 16, React 19)
        │  REST + SSE
        ▼
FastAPI backend (Python 3.12, package `app`)
        │
        ├── Routers (sessions, resume, phases, export, llm)
        ├── Agent orchestrator (4 phases)
        ├── LLM adapters (OpenAI, Anthropic, Gemini, OpenRouter, Ollama)
        ├── Parsers (pdfplumber, python-docx, plain text)
        ├── Export (WeasyPrint PDF, python-docx DOCX)
        └── Session store (Redis prod / in-memory dev)
```

**Monorepo layout:** `frontend/`, `backend/` (Python package at `backend/app/`), `docker-compose.yml`.

**Legacy note:** `backend/backend/` is an unused duplicate tree from an earlier layout. Uvicorn imports `app.*` only. Safe to delete.

---

## 5. BYOK & LLM Providers

### Bring Your Own Key

- Users enter provider, model, and API key in the browser
- Key stored in `sessionStorage` (`frontend/lib/keyStore.ts`) — cleared when the tab closes
- Sent to the backend per request as headers: `X-Api-Key`, `X-Provider`, `X-Model`
- Backend stores key ephemerally on the session (`byok_api_key`) for the SSE run; **never logged**
- Optional server-side defaults in `backend/.env` for team deployments (`has_env_key` badge in UI)

### Provider resolution (`app/llm/factory.py`)

Priority: BYOK header key → session provider/model → `.env` defaults. Placeholder values like `sk-...` in `.env.example` are ignored.

| Provider | Adapter | Structured JSON schema |
|---|---|---|
| OpenAI | `openai_adapter.py` | Native (`response_format`) |
| Gemini | `gemini_adapter.py` | Native |
| Anthropic | `anthropic_adapter.py` | Prompt injection + Pydantic parse |
| OpenRouter | `openrouter_adapter.py` | Prompt injection + Pydantic parse |
| Ollama | `ollama_adapter.py` | Prompt injection + Pydantic parse |

**Structured output:** `app/llm/structured.py` — `complete_structured()` injects JSON schema when needed, strips markdown fences, retries on parse failure (up to 3–5 attempts depending on phase).

**Context limits:** `app/llm/context.py` — `truncate_to_fit()` trims JD first, then resume chars. API enforces `MAX_RESUME_CHARS` (15,000) and `MAX_JD_CHARS` (10,000).

**Model catalog:** `app/llm/model_catalog.py` — curated lists per provider for the UI picker.

**Pricing:** `app/llm/pricing.py` — cost estimate emitted as SSE `cost_estimate` event before Phase 3.

### Adding a provider

1. Create `backend/app/llm/providers/<name>_adapter.py` implementing `LLMClient`
2. Add a `case` in `factory.py`
3. Add models to `model_catalog.py`

---

## 6. Agent Pipeline

**Orchestrator:** `backend/app/agent/orchestrator.py`

- Acquires per-phase lock (Redis `SET NX` or in-memory)
- Sets phase status → `running`
- Dispatches phase function; saves typed output; emits SSE events
- Releases lock in `finally`

| Phase | Module | Input | Output model |
|---|---|---|---|
| 1 — Keywords | `phase1_keywords.py` | `jd_raw`, `resume_raw` | `KeywordExtractionOutput` |
| 2 — Audit | `phase2_audit.py` | Phase 1 + resume + user additions | `AuditOutput` |
| 3 — Rewrite | `phase3_rewrite.py` | Phases 1–2 + resume + `UserInfo` | `TailoredResumeOutput` |
| 4 — QA | `phase4_qa.py` | Phase 3 + JD keywords + `metrics_needed` | `QAOutput` |

**Prompts:** `system_base.txt` + `phase{1,2,3,4}.txt` under `backend/app/agent/prompts/`.

**Phase-specific behavior:**

- **Phase 1:** Rejects hollow LLM output; fallback prompt with simpler schema; heuristic `present_in_resume` tagging
- **Phase 2:** `keyword_coverage` computed in Python from Phase 1 (LLM does not emit it); fallback score if LLM returns empty audit
- **Phase 3:** Emits `cost_estimate` SSE event; populates `metrics_needed` for bullets lacking user-supplied numbers
- **Phase 4:** Runs QA checklist; surfaces pass/warn/fail per item

### SSE event types

`progress`, `partial`, `cost_estimate`, `done`, `error`, `keepalive`, `stream_end`

**Flow:** Client calls `POST /api/sessions/{id}/phases/{n}/run` (202), then opens `GET .../phases/{n}/events`. If phase is already `done` and no fresh run was requested, the SSE endpoint replays cached JSON.

---

## 7. Frontend

**Framework:** Next.js 16 (App Router), React 19, Tailwind CSS 4, Radix UI primitives.

### Routes

| Path | File | Purpose |
|---|---|---|
| `/` | `app/page.tsx` | Landing |
| `/session/new?step=` | `app/session/new/page.tsx` | Input wizard |
| `/session/[id]?step=` | `app/session/[id]/page.tsx` | Agent session |

### Key components

| Component | Path |
|---|---|
| `ApiKeySettings` | `components/wizard/ApiKeySettings.tsx` |
| `LLMProviderPicker` | `components/wizard/LLMProviderPicker.tsx` |
| `ResumeUploader` | `components/wizard/ResumeUploader.tsx` |
| `JDInput` | `components/wizard/JDInput.tsx` |
| `UserInfoForm` | `components/wizard/UserInfoForm.tsx` |
| `KeywordDashboard` | `components/session/KeywordDashboard.tsx` |
| `AuditPanel` | `components/session/AuditPanel.tsx` |
| `ResumeDiff` | `components/session/ResumeDiff.tsx` |
| `InlineEditor` | `components/session/InlineEditor.tsx` |
| `VersionHistory` | `components/session/VersionHistory.tsx` |
| `QAChecklist` | `components/session/QAChecklist.tsx` |
| `ExportButtons` | `components/session/ExportButtons.tsx` |

### Client libraries

- `lib/api.ts` — typed fetch wrappers; attaches BYOK headers
- `lib/keyStore.ts` — `sessionStorage` read/write for provider/model/key
- `lib/sse.ts` — `useSSE()` hook for phase event streams

### UI notes

- `react-diff-viewer-continued` is a dependency but **side-by-side diff is not wired** — Phase 3 shows the tailored editor view
- `VersionHistory` lists snapshots; restore callback is currently a no-op in the session page
- Session page imports `ProgressLog`; wizard imports `ProviderSetup`; `ResumeDiff` imports `TailoredEditor` — these three files are **referenced but not present** in `components/` (see §17)

---

## 8. Backend & API

**Entry:** `backend/app/main.py` — CORS, structlog, optional Sentry, slowapi limiter (wired but not applied to routes).

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Status + Redis connectivity + default provider/model |
| `GET` | `/api/llm/providers` | All providers, models, `has_env_key` |
| `POST` | `/api/llm/verify` | Test provider/model/key (always 200 + `{ valid, message }`) |
| `POST` | `/api/sessions` | Create session → `{ session_id }` |
| `GET` | `/api/sessions/{id}` | Hydrate session + phase statuses/outputs |
| `PATCH` | `/api/sessions/{id}/tailored` | Overwrite full `phase3_output` |
| `POST` | `/api/sessions/{id}/resume` | Multipart upload → parse |
| `POST` | `/api/sessions/{id}/resume/text` | Paste resume text → parse |
| `POST` | `/api/sessions/{id}/userinfo` | Save `UserInfo` |
| `PATCH` | `/api/sessions/{id}/additions` | Save `user_claimed_keywords`, `user_extra_notes` |
| `POST` | `/api/sessions/{id}/jd` | Save JD (+ optional URL fetch via httpx) |
| `POST` | `/api/sessions/{id}/phases/{n}/run` | Queue phase run (202) |
| `GET` | `/api/sessions/{id}/phases/{n}/events` | SSE stream |
| `PATCH` | `/api/sessions/{id}/resume/tailored` | Inline edit + version snapshot |
| `GET` | `/api/sessions/{id}/resume/versions` | List version metadata |
| `GET` | `/api/sessions/{id}/export?format=pdf\|docx\|txt` | Download tailored resume |

**Resume parsing:** Raw text extracted with pdfplumber / python-docx, then structured via a dedicated LLM call to `ParsedResume`.

**JD URL fetch:** Basic HTTP GET; response body truncated to `MAX_JD_CHARS`. No HTML-to-text extraction.

---

## 9. Data Models

All Pydantic models under `backend/app/models/`.

### `Session`

Central state: `resume_raw`, `resume_parsed`, `user_info`, `jd_raw`, `provider`, `model`, `byok_api_key`, `user_claimed_keywords`, `user_extra_notes`, per-phase status/output, `phase3_versions`, `phase_run_requested`.

### `UserInfo`

```python
career_stage: Literal["student", "entry", "mid", "senior", "staff", "executive"]
target_role: str          # free text
is_career_transition: bool
name, email, phone, linkedin, github, certifications
```

### Phase outputs

| Model | File | Key fields |
|---|---|---|
| `KeywordExtractionOutput` | `keywords.py` | `must_have_keywords`, `nice_to_have_keywords`, `role_context` |
| `AuditOutput` | `audit.py` | `keyword_coverage`, `bullet_issues`, `overall_score`, `cliches_found` |
| `TailoredResumeOutput` | `rewrite.py` | sections + `rewrite_notes`, `metrics_needed` |
| `QAOutput` | `qa.py` | checklist items with pass/warn/fail |
| `ParsedResume` | `resume.py` | structured sections from upload |

---

## 10. Session Store

**File:** `backend/app/services/session_store.py`

| Mode | When | Backend |
|---|---|---|
| Redis | `USE_IN_MEMORY_STORE=false` (Docker default) | `redis.asyncio`, `SETEX` with session TTL |
| In-memory | `USE_IN_MEMORY_STORE=true` (local dev) | Python dict |

**Operations:** `create_session`, `get_session`, `update_session`, `save_phase_output`, `reset_phase`, `update_phase_status`, `acquire_phase_lock` / `release_phase_lock` (5-minute lock TTL).

**Lifecycle:** `init_redis()` / `close_redis()` in FastAPI lifespan.

---

## 11. Export

**File:** `backend/app/services/export_service.py`

| Format | Engine |
|---|---|
| PDF | Jinja2 template `app/templates/resume.html` → **WeasyPrint** |
| DOCX | **python-docx** (programmatic, not a template file) |
| TXT | Plain string builder |

> **Note:** `pyppeteer` is listed in `pyproject.toml` but **not used**. PDF rendering is WeasyPrint-only. The Dockerfile may install Chromium for an earlier approach — consider removing unused deps.

Requires `phase3_output` to exist before export.

---

## 12. Configuration

**Settings:** `backend/app/config.py` (loads `backend/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `openai` | Default when no BYOK headers |
| `LLM_MODEL` | `gpt-4o` | Default model |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc. | `""` | Optional server-side keys |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama |
| `REDIS_URL` | `redis://localhost:6379` | Session store |
| `USE_IN_MEMORY_STORE` | `false` in code; `true` in `.env.example` | Skip Redis for local dev |
| `SESSION_TTL_SECONDS` | `86400` | 24h |
| `SESSION_EXPIRY_WARN_SECONDS` | `72000` | Defined but only used client-side today |
| `ALLOWED_ORIGINS` | `["http://localhost:3000"]` | CORS |
| `SENTRY_DSN` | `""` | Optional error tracking |
| `MAX_RESUME_CHARS` | `15000` | |
| `MAX_JD_CHARS` | `10000` | |
| `MAX_UPLOAD_BYTES` | `5242880` (5 MB) | |

**Frontend:** `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

### Docker Compose

```yaml
services:
  redis:     redis:7-alpine
  backend:   build ./backend, port 8000, USE_IN_MEMORY_STORE=false
  frontend:  build ./frontend, port 3000
```

Run: `docker compose up` from repo root.

---

## 13. Technology Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 16, React 19, Tailwind 4, Radix UI |
| Backend | FastAPI, Python 3.12, Pydantic v2, pydantic-settings |
| LLM SDKs | openai, anthropic, google-generativeai, httpx (Ollama/OpenRouter) |
| Parsing | pdfplumber, python-docx |
| PDF export | WeasyPrint + Jinja2 |
| DOCX export | python-docx |
| Session store | Redis (prod) / dict (dev) |
| Logging | structlog (JSON) |
| Errors | sentry-sdk (optional, init only) |
| Rate limiting | slowapi (configured, not applied to routes yet) |
| Package managers | uv (Python), pnpm (Node) |

---

## 14. Repository Layout

```
smart-resume/
├── README.md
├── docker-compose.yml
├── docs/
│   └── SYSTEM_DESIGN.md          ← this file
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx
│   │   └── session/
│   │       ├── new/page.tsx
│   │       └── [id]/page.tsx
│   ├── components/
│   │   ├── wizard/               ← ApiKeySettings, ResumeUploader, JDInput, UserInfoForm, …
│   │   └── session/              ← KeywordDashboard, AuditPanel, ResumeDiff, …
│   └── lib/                      ← api.ts, keyStore.ts, sse.ts
│
└── backend/
    ├── app/                      ← import as `app.*`
    │   ├── main.py
    │   ├── config.py
    │   ├── quality_rules.py
    │   ├── agent/                ← orchestrator, phase1–4, prompts/
    │   ├── llm/                  ← factory, structured, providers/
    │   ├── models/
    │   ├── parsers/
    │   ├── routers/              ← sessions, resume, phases, export, llm
    │   ├── services/             ← session_store, export_service
    │   └── templates/resume.html
    ├── pyproject.toml
    ├── uv.lock
    └── .env.example
```

---

## 15. Security & Privacy

| Concern | Approach |
|---|---|
| Resume data | Stored in session only; 24h TTL; not written to application logs |
| BYOK keys | Ephemeral on session; forwarded to LLM APIs only; never logged |
| Session IDs | UUID v4 |
| Upload safety | 5 MB max; MIME validated server-side |
| CORS | Explicit origin allowlist |
| Input limits | Resume/JD char caps enforced at API layer |
| XSS | Resume content rendered as text; React default escaping |
| Phase concurrency | Per-session phase lock prevents duplicate runs |

---

## 16. Observability

| Signal | Status |
|---|---|
| Structured logs | **Implemented** — structlog JSON; session/phase events; no resume content in logs |
| Sentry | **Partial** — initializes when `SENTRY_DSN` is set; no custom LLM middleware |
| Health check | **Implemented** — `GET /health` includes Redis status |
| Rate limit metrics | **Not applied** — limiter exists but no `@limiter.limit` decorators |
| Phase timing | Logged at orchestrator start/end |

---

## 17. Known Gaps & Future Work

### Missing frontend files (build blockers)

These components are imported but not present under `frontend/components/`:

- `wizard/ProviderSetup.tsx` (imported by `session/new/page.tsx`)
- `session/ProgressLog.tsx` (imported by `session/[id]/page.tsx`)
- `session/TailoredEditor.tsx` (imported by `ResumeDiff.tsx`)

Restore or replace these imports before a production frontend build.

### Partial features

| Feature | Status |
|---|---|
| Side-by-side resume diff | Dependency installed; UI not wired |
| Version restore | Snapshots saved; no GET-by-id endpoint; UI restore is no-op |
| Parsed resume inline correction | Upload proceeds without edit step |
| Per-section Phase 3 regenerate | Not built |
| Rate limiting on phase endpoints | slowapi wired; decorators missing |
| Session expiry banner | Client-side 20h timer only; backend `SESSION_EXPIRY_WARN_SECONDS` unused |
| JD URL fetch | Raw HTML/text; no content extraction |
| User accounts / auth | Out of scope |

### Cleanup candidates

- Remove unused `backend/backend/` duplicate tree
- Remove or implement `pyppeteer` dependency (PDF uses WeasyPrint)
- Align `USE_IN_MEMORY_STORE` default between `config.py` (`false`) and `.env.example` (`true`)
- Align README recommended Anthropic model (`claude-opus-4-5`) with catalog (`claude-3-5-sonnet-20241022`)

### Not in repo

- Production deploy configs (Vercel, Fly.io, etc.)
- `docker-compose.dev.yml`
- Automated test suite

---

*Last updated: 2026-05-29*
