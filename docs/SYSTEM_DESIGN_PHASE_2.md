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
18. [Roadmap — Release Phase 2 & 3 (Accounts, Master Resume, ATS Guidance, Job Fit, Job Search)](#18-roadmap--release-phase-2--3)
19. [Roadmap — Release Phase 4 (Dashboard, Application Tracker, Notifications, Admin)](#19-roadmap--release-phase-4)

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

Each step maps to agent phase 1–4. Each step shows a **Run** button. Phases do not auto-trigger on navigation. Cached outputs replay automatically without re-running unless the user clicks **Re-run**.

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

---

## 18. Roadmap — Release Phase 2 & 3

> **Terminology.** The MVP described in §1–17 is **Release Phase 1**. This section covers **Release Phase 2** (auth, subscriptions, master resume, ATS guidance, job fit, cover letter — §18.1–18.9 + §18.11–18.13) and the **Release Phase 3** deliverable for Job Search (§18.10). §19 covers **Release Phase 4** (Dashboard, Tracker, Admin).
>
> Within the runtime agent we still talk about **agent phases 1–4** (Keywords, Audit, Rewrite, QA). This document always uses *Release Phase N* for product milestones and *Agent Phase N* for orchestrator phases to avoid collisions.
>
> Nothing in §18–19 affects the current implementation.

---

### 18.1 License & Intellectual Property

The repository will be published under the **Business Source License 1.1 (BSL 1.1)** at the start of Release Phase 2.

| Term | Value |
|---|---|
| License | Business Source License 1.1 |
| Licensor | Hamed Zangane |
| Licensed Work | Smart Resume Agent |
| Additional Use Grant | Free for personal, non-commercial, and internal evaluation use |
| Change Date | Five (5) years from each version's release date |
| Change License | Apache License 2.0 |
| Commercial restriction | You may not use this software to provide a commercial service to third parties without a commercial license from the Licensor |

The first public commit must include, at the repository root:

- `LICENSE` — full BSL 1.1 text
- `COMMERCIAL.md` — how organizations obtain a commercial license
- `CONTRIBUTING.md` — contribution workflow and CLA
- `CODE_OF_CONDUCT.md` — Contributor Covenant
- `SECURITY.md` — vulnerability disclosure email + GPG key + response SLA

After the Change Date, each version automatically converts to Apache 2.0, allowing unrestricted open-source use of that version.

---

### 18.2 User Accounts & Authentication

**Goal:** Replace anonymous 24-hour sessions with persistent user-owned accounts.

Authentication is mandatory in production. `AUTH_ENABLED=false` is permitted **only** in local development unit tests; the backend refuses to boot in production mode with auth disabled.

#### Registration & Login methods

| Method | Description |
|---|---|
| Email + Password | Credential registration; email must be verified within 7 days or the account is auto-suspended |
| Google SSO | One-click via NextAuth.js |
| GitHub SSO | One-click via NextAuth.js |

Clicking **Get Started Free** on the landing page goes directly to `/auth`. There is no anonymous mode in production.

#### `/auth` page

- Email + password registration with a `zxcvbn` strength meter
- Google SSO button
- GitHub SSO button
- Toggle between Register and Login
- Required checkboxes: Terms of Service + Privacy Policy
- Optional checkbox: Marketing emails
- On success → redirect to `/onboarding` (first-time) or `/dashboard`

#### Full auth flow

```
User clicks "Get Started Free"
  → /auth
  → User accepts ToS + Privacy Policy
  → NextAuth.js (Google / GitHub) OR POST /api/auth/register (email)
  → POST /api/auth/callback (OAuth) or /api/auth/register (email)
  → Upsert User in PostgreSQL
  → If email + password: send verification email (Resend, §19.5)
  → Grant 6 free credits on first registration  (§18.3)
  → Sign access JWT (15-min TTL)
  → Issue refresh token (7-day TTL, stored in httpOnly Secure cookie)
  → Bind refresh token to Redis with device fingerprint
  → Redirect to /onboarding (first-time) → /dashboard
```

#### Email verification & password reset

| Flow | Route | Behaviour |
|---|---|---|
| Send verification email | `POST /api/auth/verify/send` | Idempotent; rate-limited to 1 / 5 min |
| Confirm verification | `GET /api/auth/verify/{token}` | Token TTL 24 h; sets `email_verified_at` |
| Request password reset | `POST /api/auth/password/forgot` | Sends reset link via Resend; idempotent regardless of email existence |
| Submit new password | `POST /api/auth/password/reset` | Token TTL 1 h; invalidates **all** refresh tokens |

Email verification is required for paid features but not for spending the 6 free credits. Unverified accounts older than 7 days are soft-deleted by a daily cron job.

#### Optional 2FA (TOTP)

| Action | Route |
|---|---|
| Enroll | `POST /api/auth/2fa/enroll` — returns provisioning URI + QR data |
| Verify enrollment | `POST /api/auth/2fa/verify` |
| Disable | `POST /api/auth/2fa/disable` (requires current TOTP) |

2FA is **optional** for end users and **mandatory for admins** (§19.7). Ten one-time recovery codes are issued at enrollment and shown once.

#### New backend models (SQLAlchemy 2 / async)

```python
User(
    id: UUID,
    email: str,                          # unique; lowercased on write
    email_verified_at: datetime | None,
    email_bounced_at: datetime | None,
    display_name: str,
    auth_provider: Literal["email", "google", "github"],
    provider_id: str | None,             # OAuth subject
    password_hash: str | None,           # bcrypt (cost 12); null for SSO-only
    tier: Literal["free", "pro"],
    credit_balance: int,
    byok_api_key: bytes | None,          # AES-256-GCM encrypted at rest
    byok_provider: str | None,
    byok_key_fingerprint: str | None,    # SHA-256 of plaintext for admin display
    totp_secret: bytes | None,           # AES-256-GCM encrypted; null = 2FA off
    totp_recovery_codes: list[str],      # SHA-256 hashed
    trials_used: int,                    # one free trial per user (§18.3)
    closure_requested_at: datetime | None,   # §19.6
    suspended_at: datetime | None,           # §19.7
    suspension_reason: str | None,
    accepted_tos_version: str,           # e.g. "2026-06"
    marketing_opt_in: bool,
    created_at: datetime,
    last_login_at: datetime,
    last_login_ip: str | None,
    blocked_companies: list[str],        # for /jobs filtering (§18.10)
)

RefreshToken(
    id: UUID,
    user_id: UUID,
    token_hash: str,                     # SHA-256(token)
    device_fingerprint: str,             # UA + IP hash
    issued_at: datetime,
    expires_at: datetime,
    revoked_at: datetime | None,
)
```

#### New auth routes

```
POST /api/auth/register                  — email + password registration
POST /api/auth/login                     — email + password login (2FA challenge if enrolled)
POST /api/auth/callback                  — OAuth callback (Google / GitHub)
POST /api/auth/logout                    — revoke current refresh token
POST /api/auth/logout-all                — revoke all refresh tokens for user
POST /api/auth/refresh                   — rotate refresh token + issue new access JWT
POST /api/auth/verify/send               — resend verification email
GET  /api/auth/verify/{token}            — confirm email
POST /api/auth/password/forgot           — request reset email
POST /api/auth/password/reset            — submit new password
POST /api/auth/2fa/enroll                — TOTP enrollment start
POST /api/auth/2fa/verify                — TOTP enrollment confirm
POST /api/auth/2fa/disable               — disable 2FA
GET  /api/auth/me                        — current user + credits + tier
GET  /api/auth/sessions                  — list active refresh tokens (devices)
DELETE /api/auth/sessions/{id}           — revoke a specific device session
```

#### Security rules

- `user_id` is always read from the verified access JWT — never from the request body
- All DB queries are scoped by `user_id`
- BYOK API keys are encrypted with AES-256-GCM using a key from `BYOK_ENCRYPTION_KEY` (KMS-backed in production); decrypted only at LLM call time; never logged
- Access JWT signed HS256 with `AUTH_SECRET`; **15-min TTL; no sliding renewal** — clients always exchange refresh tokens
- Refresh tokens **rotate on every use**; replay of a revoked refresh token revokes the entire token chain (refresh-reuse detection)
- bcrypt cost factor 12; passwords ≥ 10 chars with zxcvbn score ≥ 3
- Rate limits via slowapi: `/auth/login` 10 / min / IP, `/auth/register` 5 / min / IP, `/auth/password/forgot` 3 / min / IP, `/auth/refresh` 30 / min / token
- 5 failed logins in 15 min → temporary lockout + "suspicious login" email
- All auth events recorded in `AuthAuditLog` (§19.7) and surfaced to admin

---

### 18.3 Credit & Subscription System

**Goal:** Give every user a meaningful free trial, then convert them to a subscription. Subscriptions are *period-quota* (not credit-based) within tier limits; free users are credit-based.

#### Free tier (registration grant)

Every new account receives **6 credits** on registration.

| Action | Credits consumed |
|---|---|
| Resume build (Agent Phases 1–4) | 1 credit |
| ATS recalculation (Agent Phase 4 only, against an existing tailored resume) | 1 credit |
| Cover letter generation (§18.11) | 1 credit |
| Per-section / per-bullet regeneration (§18.5) | 1 credit |
| Job search / Job Fit analysis | ❌ Not available on free credits |

6 credits ≈ 6 actions (e.g. 4 resume builds + 2 recalculations). No job search until subscribed.

#### Subscription tiers

| Plan | Price | Resumes / period | Job searches / period | Yearly cycle (−20 %) | Default LLM cost / resume | Gross margin* |
|---|---|---|---|---|---|---|
| **Daily** | $2.99 / day | 40 | 10 | — | ~$0.004 | 94 % |
| **Weekly** | $9.99 / week | 280 | 70 | — | ~$0.004 | 89 % |
| **Monthly** | $19.99 / month | 150 | 300 | $191.90 / yr | ~$0.004 | 94 % |

\* Gross margin = (price − Σ default LLM cost at max usage) / price. **Excludes** Stripe fees (~2.9 % + $0.30) and shared infra (§18.12).

**Yearly is a billing cycle, not a separate plan.** `Subscription.plan = "monthly"` with `Subscription.billing_cycle = "yearly"` represents a yearly subscription to the Monthly plan at a 20 % discount. There is no standalone "yearly" tier.

#### LLM quality upgrade (add-on, Agent Phase 3 only)

Three model tiers for the rewrite call — the only call where model quality measurably changes user outcomes.

| Tier | Model | Per-resume / pack | Monthly add-on | Yearly add-on (−20 %) |
|---|---|---|---|---|
| **Standard** (default) | Gemini 2.5 Flash-Lite | included | — | — |
| **Better** | Gemini 2.5 Flash | $4.49 / 5-pack (≈ $0.898 each) | +$4.99 / mo | +$47.90 / yr |
| **Best** | Claude Sonnet 4.6 | $2.99 / resume | +$12.99 / mo | +$124.99 / yr |

These prices are the **single source of truth** and supersede any earlier draft. The same four numbers (pack, per-resume, monthly, yearly) appear in §18.9 and `LLMConfig` (§19.7) — all three locations must match for the price-display contract to hold.

**Best monthly soft-cap:** the Best add-on is limited to **100 upgraded resumes per period**. Runs 101–150 silently fall back to Standard with a UI banner. Tracked via `Subscription.upgraded_resumes_used`. Enforced in the Agent Phase 3 orchestrator middleware before the LLM call — not in Stripe.

**Yearly add-on rule:** a yearly LLM add-on is only valid when the base subscription cycle is also yearly. The API returns `HTTP 409 {"code": "billing_cycle_mismatch"}` on mismatch.

**The single $0.99 Better per-resume option is retired** — Stripe fees made it uneconomical. Any legacy Stripe price ID for `better_single` returns `HTTP 410 Gone` with a redirect to the 5-pack purchase URL.

#### BYOK users

Users who supply their own LLM API key bypass platform LLM costs entirely. They still pay a subscription for infrastructure, job search, and embedding access (embeddings always use the platform OpenAI key). BYOK users see a "Your keys" badge in the UI and a token / cost estimate per run. BYOK users cannot purchase platform LLM tier upgrades because the upgrade *is* the platform-paid model.

#### Refunds

| Trigger | Policy |
|---|---|
| Within 24 h of first paid charge | Self-service full refund via Stripe |
| Within 7 days, no usage in the period | Self-service full refund |
| After 7 days OR with usage | Manual refund request via `/dashboard/billing/support`; super-admin approval |
| Failed payment, never had access | Stripe auto-reverses |
| Plan downgrade mid-period | No proration; takes effect next renewal |
| Plan upgrade mid-period | Stripe pro-rates and charges immediately |
| Chargeback | `RefundRecord.reason = "chargeback"`; user auto-suspended pending review |

All refunds are recorded in `RefundRecord` and surface in admin reports + the user's billing history.

#### Payment failure & grace period

When Stripe fires `invoice.payment_failed`:

| Day | Behaviour |
|---|---|
| Day 0 (failure) | `Subscription.status = "grace"`; `payment_failed_at = now()`; email + in-app notification |
| Days 1–3 | Full access retained; banner: "Payment failed — update your card to avoid interruption" |
| Day 1 | Second retry email + Stripe auto-retry |
| Day 3 | Final email; at end of day `status = "expired"`; new runs blocked; existing outputs remain readable per §19.2 |
| Any day before Day 3 | User updates card → `invoice.payment_succeeded` → `status = "active"`; clear `payment_failed_at`; "Payment restored" notification |

#### Free trial (admin-controlled)

A 7-day free trial of any subscription cycle can be enabled per Stripe price ID via the admin panel (§19.7). When enabled, new subscribers get full plan benefits with no charge for 7 days, then auto-convert unless they cancel. Trials are limited to **one per user account** (tracked via `User.trials_used`). Stripe handles trial state via `subscription.status = "trialing"`.

#### Credit / quota routing logic

```
Request arrives
  └─ Is user suspended? → HTTP 403
  └─ Is the action a paid action (build / recalc / search / fit / cover letter)?
       └─ NO  → run; no decrement
       └─ YES → Is the user subscribed and within plan limits?
                  ├─ YES → run; increment the right period counter
                  └─ NO  → Is the action allowed on free credits AND credits ≥ cost?
                            ├─ YES → decrement credits; run
                            └─ NO  → HTTP 402 Payment Required with upgrade JSON
```

#### New backend models

```python
Subscription(
    id: UUID,
    user_id: UUID,
    plan: Literal["daily", "weekly", "monthly"],
    billing_cycle: Literal["recurring", "yearly"],          # yearly = -20% off monthly
    llm_upgrade: Literal["standard", "better", "best"],
    llm_upgrade_billing_cycle: Literal["per_pack", "monthly", "yearly"] | None,
    status: Literal["trialing", "active", "paused", "cancelled", "expired", "grace"],
    trial_ends_at: datetime | None,
    period_start: datetime,
    period_end: datetime,
    resumes_used: int,            # resets each period
    searches_used: int,           # resets each period
    upgraded_resumes_used: int,   # Best soft-cap counter; resets each period
    paused_at: datetime | None,                # §19.8
    pause_resumes_at: datetime | None,         # max 90 days
    payment_failed_at: datetime | None,
    cancelled_at: datetime | None,
    cancel_at_period_end: bool,
    stripe_customer_id: str,
    stripe_subscription_id: str,
    stripe_price_id: str,
    created_at: datetime,
)

CreditTransaction(
    id: UUID,
    user_id: UUID,
    amount: int,                  # positive = grant; negative = consumption
    action: Literal[
        "registration_grant",     # +6
        "resume_build",           # -1
        "ats_recalc",             # -1
        "cover_letter",           # -1
        "section_regen",          # -1
        "llm_upgrade_pack",       # +5  (Better 5-pack purchase)
        "llm_upgrade_pack_use",   # -1  (Better pack credit consumed)
        "admin_grant",            # +N  (manual)
        "admin_revoke",           # -N  (manual)
        "refund_reverse",         # +N  (when a paid action is refunded)
    ],
    session_id: str | None,
    admin_id: UUID | None,        # set for admin_grant / admin_revoke
    note: str | None,
    created_at: datetime,
)

RefundRecord(
    id: UUID,
    user_id: UUID,
    subscription_id: UUID | None,
    stripe_refund_id: str,
    amount_usd: float,
    reason: Literal["self_service_24h", "self_service_unused", "manual", "chargeback"],
    initiated_by: Literal["user", "system", "admin"],
    admin_id: UUID | None,
    created_at: datetime,
)
```

#### New subscription & credit routes

```
GET  /api/credits/balance                    — free credits remaining + subscription summary
GET  /api/credits/transactions               — paginated history
POST /api/subscriptions/checkout             — Stripe checkout session for a plan
POST /api/subscriptions/portal               — Stripe billing portal session (cards, invoices)
POST /api/subscriptions/cancel               — cancel at period end
POST /api/subscriptions/resume               — un-cancel before period end
POST /api/subscriptions/change-plan          — upgrade (proration) or downgrade (next renewal)
POST /api/subscriptions/pause                — pause up to 90 days (§19.8)
POST /api/subscriptions/unpause              — end pause early
GET  /api/subscriptions/current              — current plan + usage counters
POST /api/subscriptions/llm-upgrade/checkout — Stripe checkout for an LLM tier add-on
POST /api/subscriptions/refund-request       — submit manual refund request (queued for admin)
POST /api/webhooks/stripe                    — Stripe webhook receiver (signature-verified)
```

---

### 18.4 Master Resume (Profile Document)

**Goal:** User uploads one master document containing everything they may ever put on a resume. The agent selects only the content most relevant to the current JD during Agent Phase 3.

#### Storage

```python
MasterResume(
    id: UUID,
    user_id: UUID,                          # unique — one master resume per user
    raw_text: str,                          # last uploaded text
    parsed_sections: JSON,                  # structured sections extracted by LLM
    chunk_count: int,
    last_embedded_at: datetime,
    updated_at: datetime,
)

MasterResumeChunk(
    id: UUID,
    master_resume_id: UUID,
    section_type: Literal[
        "summary", "experience", "skills", "education",
        "project", "cert", "publication", "award",
        "volunteer", "language", "patent", "other",
    ],
    content: str,                           # 1 chunk = 1 logical bullet/section
    token_count: int,                       # tiktoken length for cost calc
    embedding: vector(1536),                # pgvector ivfflat; text-embedding-3-small
    metadata: JSON,                         # e.g. {"company":"Acme","year":2024,"tags":["Python"]}
    deleted_at: datetime | None,            # soft delete
    created_at: datetime,
)
```

#### Chunking policy

| Section type | Chunk granularity | Max chars per chunk |
|---|---|---|
| `experience` | One chunk per bullet | 800 |
| `project` | One chunk per project (header paragraph + bullets) | 1,500 |
| `skills` | Grouped chunks by category (e.g. "Languages", "Cloud") | 400 |
| `education` | One chunk per institution | 600 |
| `cert`, `publication`, `award`, `patent`, `language` | One chunk per item | 400 |
| `summary` | Whole summary as one chunk | 1,000 |

Chunks exceeding the cap are split on sentence boundaries with 50-char overlap. Token counts are stored for prompt-budget accounting.

#### Vector similarity selection (runs before Agent Phase 3)

```
1. Embed JD requirements → vector (text-embedding-3-small)
2. Query MasterResumeChunk by cosine similarity (pgvector ivfflat index)
3. Return top-K chunks above similarity threshold (default: 0.72; admin-tunable §19.7)
4. Group chunks by section_type and re-rank within group by score
5. Apply per-section caps (e.g. ≤ 8 experience, ≤ 4 project) to fit prompt budget
6. Pass selected chunks to Phase 3 prompt as "available content"
7. Phase 3 LLM composes from those chunks only — never invents new content
8. Return selected_chunk_ids + skipped_chunk_ids in TailoredResumeOutput for transparency
```

Chunks below the threshold are excluded from the prompt entirely — the LLM never sees irrelevant content. The skipped list is returned to the UI so users can manually pull chunks back in via "Add Section → Pull from master" (§18.5).

#### Re-embedding strategy

- `PUT /api/profile/resume` (full replace) → re-embed all chunks
- `PATCH /api/profile/resume/chunks/{id}` (single-chunk edit) → re-embed that chunk only
- Embedding cost is estimated from token counts and shown before save

#### Selected vs skipped transparency

`TailoredResumeOutput` gains a `selected_sections` field listing every master resume chunk considered, its similarity score, and whether it was used.

#### New master resume routes

```
POST /api/profile/resume                  — upload or paste; chunking + embedding
GET  /api/profile/resume                  — raw text + parsed sections + last_embedded_at
PUT  /api/profile/resume                  — full replace; re-embeds all chunks
PATCH /api/profile/resume/chunks/{id}     — edit a single chunk; re-embed just that one
DELETE /api/profile/resume/chunks/{id}    — soft delete
GET  /api/profile/resume/chunks           — list chunks; optional ?jd_session_id= returns similarity scores
```

#### New frontend page: `/profile`

- Upload (PDF / DOCX / TXT) or paste master resume
- View parsed sections grouped by `section_type`, with chunk count and last-embedded timestamp
- Inline edit per chunk with token count + cost estimate
- "Re-embed all" button (shown only when many chunks have been edited)
- Side panel: "Used in N tailored resumes" with deep links to those resumes

---

### 18.5 Tailored Rewrite Page Enhancements

**Goal:** Give users full editorial control on the Agent Phase 3 output before exporting.

#### Add Section — two modes

| Mode | Description |
|---|---|
| **Pull from master resume** | Shows skipped master resume chunks (from §18.4) with similarity score; user selects one to insert |
| **Write manually** | Free-text editor to add a new section from scratch |

Both modes append a section to the current `TailoredResumeOutput` and trigger a version snapshot.

#### Regenerate single section / single bullet

- Each section header has a "↻ Regenerate" action → re-runs Agent Phase 3 scoped to that section
- Each bullet has a "↻ Regenerate bullet" action → smaller scoped LLM call against the bullet + JD keywords + master chunks
- Cost: **1 credit** for free users; subscribers' regenerations do **not** consume `resumes_used`

#### Recalculate ATS Score

- Button calls `POST /api/sessions/{id}/phases/4/run` against the current edited state
- Streams Agent Phase 4 results via SSE
- Updates the live ATS score badge and the ATS Guidance panel (§18.7)
- Cost: **1 credit** for free users; recalcs do **not** consume `resumes_used` for subscribers

#### Undo / redo

- Up to 20 in-session edits maintained in memory (not persisted)
- Persisted `phase3_versions` snapshots remain the source of truth across reloads

#### Live ATS score badge

Visible at all times on the Agent Phase 3 page. Updates after every recalculation.

---

### 18.6 Free Navigation Between Agent Phases

**Goal:** Users can move freely between Agent Phase 2 (Audit), 3 (Rewrite), and 4 (QA & Export) without losing work.

#### Navigation model

```
Agent Phase 1 (one-time entry) → Phase 2 ↔ Phase 3 ↔ Phase 4
```

Agent Phase 1 remains a one-time step per session. Re-running Phase 1 requires creating a new session (which is one click from the existing session header).

#### Stale phase rule

If a user edits a phase's input, the downstream phases are flagged **stale**:

| Edit action | Phases marked stale |
|---|---|
| Edit Phase 2 (Audit) output | Phase 3, Phase 4 |
| Edit Phase 3 (Rewrite) output | Phase 4 |
| Recalculate ATS (Phase 4 only) | None |

A banner appears on stale phases: *"Your audit changed. Re-run Phase 3 to apply updates."* Existing outputs are preserved and still visible. **Re-run is always explicit** — navigation never triggers auto-run.

#### Step navigation UI

- After Phase 1 completion, Phase 2 / 3 / 4 tabs are always clickable
- Stale phases show a yellow warning dot on the step tab
- The Re-run button is prominent on each phase page

---

### 18.7 ATS Score Guidance

**Goal:** After every Agent Phase 4 run or recalculation, tell the user exactly what is preventing a higher ATS score and how to fix it.

#### Naming: which "score"?

- `AuditOutput.overall_score` (Agent Phase 2) is a **diagnostic** score on the *original* resume vs the JD — used by the audit dashboard
- `QAOutput.ats_score` (Agent Phase 4) is the **final** score on the *tailored* resume — displayed in the live badge (§18.5) and in dashboards

The two are deliberately separate. The UI labels them "Audit score" and "ATS score" respectively. No place in the codebase should overload either name.

#### Extended `QAOutput` model

```python
class BlockingIssue(BaseModel):
    category: Literal["keyword", "bullet", "metric", "format", "length", "section"]
    description: str        # what is wrong
    suggestion: str         # specific action to fix it
    impact: Literal["high", "medium", "low"]
    fix_effort: Literal["one_click", "user_input", "manual_rewrite"]

class QAOutput(BaseModel):
    # ... existing fields ...
    ats_score: int                          # 0–100, tailored resume
    blocking_issues: list[BlockingIssue]    # ordered by impact desc, then fix_effort asc
    score_ceiling: int                      # max achievable given current JD + master resume
    quick_wins: list[BlockingIssue]         # subset where impact=high AND fix_effort=one_click
```

#### Guidance is generated inside the Phase 4 prompt

The Phase 4 prompt is extended to emit `ats_score`, `blocking_issues`, `score_ceiling`, and `quick_wins` as part of its structured JSON output — not post-processed. The LLM produces the analysis directly against the tailored resume + JD.

#### ATS Guidance panel (frontend)

Displayed on Phase 3 and Phase 4 pages. Updates after every recalculation.

| Section | Content |
|---|---|
| Score | Large badge (e.g. 74 / 100) and ceiling (e.g. *"Up to 91 achievable"*) |
| Quick wins | High-impact / one-click suggestions at top with "Apply" buttons that pre-fill edits |
| Blocking issues | Full list, ordered by impact then effort; category + description + concrete suggestion |
| Trend | Sparkline of the last 5 ATS scores for this resume (after each recalc) |

---

### 18.8 Job Fit Analysis

**Goal:** Allow a subscribed user to paste, upload, or link a job and instantly see how well their full profile matches it — before committing to a full resume tailoring session.

#### How it works

```
User submits JD (paste / upload / URL)
  → Server loads MasterResumeChunk rows for the user
  → Embed JD → cosine match against MasterResumeChunk (pgvector)
  → Top-K chunks + JD passed to Gemini 2.5 Flash-Lite
  → Returns FitAnalysisOutput
  → Frontend renders fit score, match breakdown, gap list, recommendation
  → (Optional) Hirebase /v2/jobs/vsearch to surface similar jobs
```

Hirebase is **not required** for Fit itself — local pgvector matching is sufficient. Hirebase is only used when the user clicks "Find similar jobs", which routes them to `/jobs?seed_fit_id=…` (Release Phase 3).

#### Requires

- Saved master resume (account required)
- Active subscription (not available on free credits)
- Counts as **1 search** against `Subscription.searches_used`
- Rate-limited to **20 / hour / user**

#### `FitAnalysisOutput` model

```python
class SectionFit(BaseModel):
    section_type: str
    match_score: int                    # 0–100
    matched_items: list[str]
    missing_items: list[str]

class FitAnalysisOutput(BaseModel):
    overall_fit_score: int              # 0–100
    fit_label: Literal["strong", "good", "partial", "weak"]
    section_fits: list[SectionFit]
    key_gaps: list[str]                 # top 5 things missing from profile
    key_strengths: list[str]            # top 5 matching strengths
    recommendation: str                 # 2–3 sentence summary
    should_apply: bool
    suggested_master_resume_edits: list[str]   # concrete bullets to add to master resume
```

#### New routes

```
POST /api/fit/analyze                 — submit JD; FitAnalysisOutput via SSE
GET  /api/fit/history                 — paginated past analyses
GET  /api/fit/{id}                    — full analysis detail
```

#### New frontend page: `/fit`

- Input: paste JD text, upload file, or enter a URL
- Output: fit score gauge, section-by-section breakdown, key gaps, key strengths, recommendation
- Primary CTA: *"Tailor my resume for this job"* → pre-fills JD in `/session/new`
- Secondary CTA: *"Find similar jobs"* → calls Hirebase `vsearch` and opens `/jobs?seed_fit_id=…`
- Tertiary CTA: *"Add suggested bullets to my master resume"* → bulk-insert into `/profile`

---

### 18.9 LLM Routing Strategy

**Goal:** Use the most cost-effective model for every task by default, with user-selectable upgrades for higher quality on Agent Phase 3 only.

#### Default platform model routing

| Task | Model | Cost per call | Reason |
|---|---|---|---|
| Agent Phase 1 — Keywords | Gemini 2.5 Flash-Lite | ~$0.0005 | Fast, cheap, structured |
| Agent Phase 2 — Audit | Gemini 2.5 Flash-Lite | ~$0.0007 | Fast, cheap, structured |
| Agent Phase 3 — Rewrite | Gemini 2.5 Flash-Lite | ~$0.0014 | Default; upgradeable per §18.3 |
| Agent Phase 4 — QA + Guidance | Gemini 2.5 Flash-Lite | ~$0.0009 | Fast, cheap, structured |
| Job Fit analysis | Gemini 2.5 Flash-Lite | ~$0.0008 | LLM only summarizes; matching is local pgvector |
| Cover letter (§18.11) | Gemini 2.5 Flash-Lite | ~$0.0010 | Default; honors user's Phase 3 upgrade tier |
| Embeddings | text-embedding-3-small | ~$0.00007 | Platform-managed; never BYOK |

**Total default platform cost per full resume run: ~$0.0036** (sum of Agent Phases 1–4)

#### LLM upgrade options (Agent Phase 3 only)

| Tier | Model | Cost / resume | Pack price | Monthly add-on | Yearly add-on (−20 %) |
|---|---|---|---|---|---|
| Standard (default) | Gemini 2.5 Flash-Lite | ~$0.0014 | included | — | — |
| Better | Gemini 2.5 Flash | ~$0.0085 | $4.49 / 5-pack ($0.898 each) | +$4.99 / mo | +$47.90 / yr |
| Best | Claude Sonnet 4.6 (`claude-sonnet-4-6`) | ~$0.051 | $2.99 / resume | +$12.99 / mo | +$124.99 / yr |

These prices match §18.3 exactly and are the canonical source. They must remain in sync with `LLMConfig` rows seeded for §19.7 — automated tests verify the three locations agree.

> **Model lifecycle:** `claude-sonnet-4-20250514` is retired on 2026-06-15. All Anthropic calls must use `claude-sonnet-4-6`. The orchestrator reads the model string from `LLMConfig` at request time — **never hardcoded**.

BYOK users supply their own key for Agent Phases 1–4. Embeddings always use the platform OpenAI key regardless of BYOK status. BYOK users cannot purchase Better / Best platform upgrades because the upgrade *is* the platform-paid model.

---

### 18.10 Job Search (Release Phase 3 Deliverable)

**Goal:** Let subscribed users search for jobs directly inside the app, with real-time fresh results and a cached layer to minimize API costs.

> **Roadmap note.** Job Search ships in **Release Phase 3** (2026 Q4), after Release Phase 2 (auth + subscriptions + master resume + ATS guidance) has hardened. The architecture is described here for planning continuity.

#### Two-layer architecture

```
User submits a job search query
  └─ Normalize query (lowercase, trim, collapse synonyms via small dictionary)
  └─ Is it a cached common search < 1 hour old?
       ├─ YES → Serve from PostgreSQL job_cache  ($0 cost)
       └─ NO  → Call Hirebase API → cache result → serve
                  └─ Cost: ~$0.002 per unique search

Background worker (AWS Lambda, hourly via EventBridge)
  └─ Top 100 common queries (seeded from JobSearchLog)
  └─ Fetch via Apify Google Jobs scraper → write to PostgreSQL job_cache
  └─ Worst-case cost: 100 queries × 10 results × $0.003 ≈ $3 / day
  └─ Practical (overlapping queries): ~$45 / month
```

#### Why two providers

| Provider | Role | Why |
|---|---|---|
| **Hirebase** | Real-time unique-user searches | Semantic vector search built-in; free tier 500 / month; $79 / month paid; 2 M+ live jobs updated within 24 h; AI spam filtering removes ~60 % expired listings |
| **Apify Google Jobs** | Hourly background cache | $0.003 / result; covers Indeed, LinkedIn, Glassdoor, ZipRecruiter, company career pages; no subscription |

#### Hirebase semantic search

Hirebase `/v2/jobs/vsearch` finds jobs by semantic similarity. It accepts a natural-language query, a `job_id` for similar-job discovery, or an `artifact_id` to match jobs against an uploaded resume directly. We use this for:

- Keyword search (role + location)
- "Find jobs similar to my resume" (upload artifact once; cached server-side)
- "Find similar jobs" CTA from `/fit`

#### Hirebase circuit breaker

| Condition | Action |
|---|---|
| 5 consecutive failures or HTTP 429 / 5xx within 60 s | Circuit opens |
| Circuit open | Serve from PostgreSQL cache; banner "Results may not be fully up to date" |
| Cool-down | 5 min, then one probe |
| Probe succeeds | Circuit closes |
| Probe fails | Remain open; reset 5-min cool-down |
| Cache miss during outage | Empty results + friendly message; **do not** decrement `searches_used` |

#### Deduplication & normalization

- **Dedup key:** `lower(company) + lower(title) + city + posted_date_floor("day")`
- Duplicate rows collapse to one with `sources` array (`["hirebase", "apify"]`)
- Salary ranges normalized to USD using a daily FX cache
- Locations split into `location_city` + `location_country` via a lightweight geocoder library

#### Saved searches & job alerts

| Capability | Behaviour |
|---|---|
| Save a search | `POST /api/jobs/saved-searches` with query + filters |
| Alert frequency | `off | daily | weekly` per saved search |
| Delivery | Email + in-app (§19.5) |
| Limits | 10 saved searches / user; max 5 with alerts enabled |

#### Blocked / blacklisted companies

Per-user preference list. Companies are hidden from results (cached or live). Stored in `User.blocked_companies`. Editable on `/jobs/preferences`.

#### Job data models

```python
JobCache(
    id: UUID,
    sources: list[Literal["hirebase", "apify"]],
    external_ids: dict[str, str],          # {"hirebase": "...", "apify": "..."}
    title: str,
    company: str,
    company_normalized: str,               # indexed
    location: str,
    location_city: str | None,
    location_country: str | None,
    remote: bool,
    salary_min_usd: int | None,
    salary_max_usd: int | None,
    salary_currency_original: str | None,
    employment_type: str,
    posted_date: datetime,
    description: str,
    apply_url: str,
    raw_json: JSON,
    cached_at: datetime,
    expires_at: datetime,                  # 1 h common cache; 24 h unique searches
    dedup_key: str,                        # unique index
)

JobSearchLog(
    id: UUID,
    user_id: UUID,
    query: str,
    location: str | None,
    filters: JSON,
    result_count: int,
    source: Literal["cache", "hirebase", "apify"],
    cost_usd: float,
    created_at: datetime,
)

SavedSearch(
    id: UUID,
    user_id: UUID,
    name: str,
    query: str,
    location: str | None,
    filters: JSON,
    alert_frequency: Literal["off", "daily", "weekly"],
    last_alerted_at: datetime | None,
    created_at: datetime,
)
```

#### New job search routes

```
POST /api/jobs/search                       — keyword / natural-language search; paginated
POST /api/jobs/match                        — match jobs to master resume via Hirebase vsearch
GET  /api/jobs/{id}                         — full detail
POST /api/jobs/{id}/fit                     — run fit analysis against master resume
POST /api/jobs/{id}/save                    — bookmark a job
DELETE /api/jobs/{id}/save                  — unbookmark
GET  /api/jobs/saved                        — saved jobs list
GET  /api/jobs/saved-searches               — list saved searches
POST /api/jobs/saved-searches               — create
PATCH /api/jobs/saved-searches/{id}         — edit (name / filters / alert frequency)
DELETE /api/jobs/saved-searches/{id}        — delete
GET  /api/jobs/preferences                  — blocked companies + global filters
PUT  /api/jobs/preferences                  — update preferences
```

Rate limits: `/api/jobs/search` — 60 / hour / user. `/api/jobs/{id}/fit` — inherits the §18.8 fit rate limit.

#### New frontend page: `/jobs`

- Search bar: role + location + remote toggle + date posted + salary min + employment type
- Filter chips for blocked companies (managed in `/jobs/preferences`)
- Result cards: title, company, location, salary, posted date, source badge, remote tag
- Card actions: **Check Fit** → inline fit score; **Tailor Resume** → pre-fills JD in `/session/new`; **Save** → bookmark
- Non-subscribers see a locked state with upgrade CTA

#### New environment variables (Release Phase 3)

```
HIREBASE_API_KEY=
APIFY_API_TOKEN=
APIFY_ACTOR_ID=automation-lab/google-jobs-scraper
JOB_CACHE_TTL_COMMON_SECONDS=3600
JOB_CACHE_TTL_UNIQUE_SECONDS=86400
```

#### New infrastructure (Release Phase 3)

| Addition | Purpose |
|---|---|
| AWS Lambda (scheduled via EventBridge) | Hourly Apify background cache worker |
| AWS SQS | Decouples Lambda fetch from PostgreSQL writes |
| AWS Lambda (alert dispatcher, daily/weekly cron) | Saved-search alert emails |
| PostgreSQL `job_cache`, `job_search_log`, `saved_search` tables | Storage |
| Hirebase API | Real-time semantic job search |
| Apify Google Jobs | Background cache population |

#### Extra monthly infrastructure cost (Release Phase 3)

| Item | Cost |
|---|---|
| Hirebase (free tier, ≤ 500 unique searches) | $0 |
| Hirebase (paid, as traffic grows) | $79 |
| Apify hourly background cache | ~$45 |
| AWS Lambda + SQS + EventBridge | ~$5 |
| **Total extra at launch** | **~$5 / month** |
| **Total extra at scale** | **~$129 / month** |

---

### 18.11 Cover Letter Generator

**Goal:** Generate a job-specific cover letter from the same session inputs (JD + tailored resume + UserInfo + tone preference). Optional add-on to every resume run.

#### Trigger points

- A "Generate cover letter" button appears on Agent Phase 4 (after QA passes)
- A standalone page `/cover-letter/new?session_id=…` for users who only want the letter

#### Inputs

- Tailored `TailoredResumeOutput` from the session
- JD from the session
- `UserInfo` (name, phone, etc.)
- Tone selector: `formal | balanced | warm`
- Optional custom hook (e.g. "I admire your work on X")

#### Output model

```python
CoverLetterOutput(
    body_markdown: str,
    body_plain: str,
    word_count: int,
    tone: Literal["formal", "balanced", "warm"],
    keywords_used: list[str],
)
```

#### Cost

- Single LLM call (Standard / Better / Best follows the user's Phase 3 upgrade tier)
- **1 credit** for free users
- Bundled with the matching resume run for subscribers — does **not** consume `resumes_used`

#### Export

- DOCX (python-docx) and PDF (WeasyPrint) reusing the existing export pipeline
- TXT also available

#### New routes

```
POST /api/sessions/{id}/cover-letter                 — generate (SSE)
GET  /api/sessions/{id}/cover-letter                 — fetch latest
GET  /api/sessions/{id}/cover-letter/export?format=pdf|docx|txt
```

---

### 18.12 Infrastructure Additions (Release Phase 2)

#### New services (`docker-compose.yml`)

```yaml
postgres:
  image: pgvector/pgvector:pg16       # bundles the vector extension; no init SQL needed
  environment:
    POSTGRES_DB: smart_resume
    POSTGRES_USER: smart_resume
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
  volumes:
    - pgdata:/var/lib/postgresql/data

redis:
  # existing service — no changes

backend:
  # existing service; adds DATABASE_URL, AUTH_SECRET, BYOK_ENCRYPTION_KEY, STRIPE_*, RESEND_*
```

(Job-search-specific Lambda / SQS / Hirebase / Apify infrastructure ships in Release Phase 3 — see §18.10.)

#### Full environment variables (Release Phase 2)

```
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://smart_resume:password@postgres:5432/smart_resume

# Auth
AUTH_ENABLED=true                       # production MUST be true; false only for local dev unit tests
AUTH_SECRET=<random 32-byte hex>        # JWT signing
BYOK_ENCRYPTION_KEY=<random 32-byte hex>  # AES-256-GCM for BYOK keys + TOTP secrets
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# Embeddings (platform-managed; never exposed to users)
OPENAI_EMBEDDING_KEY=

# Stripe (subscriptions + add-ons)
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_DAILY=price_…
STRIPE_PRICE_WEEKLY=price_…
STRIPE_PRICE_MONTHLY=price_…
STRIPE_PRICE_MONTHLY_YEARLY=price_…
STRIPE_PRICE_BETTER_PACK=price_…
STRIPE_PRICE_BETTER_MONTHLY=price_…
STRIPE_PRICE_BETTER_YEARLY=price_…
STRIPE_PRICE_BEST_PER_RESUME=price_…
STRIPE_PRICE_BEST_MONTHLY=price_…
STRIPE_PRICE_BEST_YEARLY=price_…

# Email (Resend) — used by §18.2 verification, §18.3 billing, §19.5 notifications
RESEND_API_KEY=
RESEND_FROM_EMAIL=noreply@zanganehai.com

# Admin bootstrap (one-time; ignored after first super-admin exists)
BOOTSTRAP_SUPER_ADMIN_EMAIL=
ADMIN_INVITE_TTL_SECONDS=604800

# Observability
SENTRY_DSN=
LOG_LEVEL=INFO
```

#### Database safety

- All migrations go through Alembic and are reviewed in PR before merge
- Daily PostgreSQL backups to S3, retained 30 days
- Point-in-time recovery enabled on RDS in production
- Schema-level FK + cascade rules; no orphaned rows

#### Default rate limits (slowapi)

| Endpoint group | Limit |
|---|---|
| `/api/auth/login` | 10 / min / IP |
| `/api/auth/register` | 5 / min / IP |
| `/api/auth/password/forgot` | 3 / min / IP |
| `/api/auth/refresh` | 30 / min / token |
| `/api/sessions/{id}/phases/*/run` | 10 / min / user |
| `/api/fit/analyze` | 20 / hour / user |
| `/api/jobs/search` (Release Phase 3) | 60 / hour / user |
| All other authenticated routes | 120 / min / user |

#### Complete new technology additions (Release Phase 2)

| Addition | Purpose |
|---|---|
| PostgreSQL 16 + pgvector | Persistent user data + vector similarity search |
| SQLAlchemy 2 (async) + asyncpg | Async ORM |
| Alembic | Database migrations |
| NextAuth.js | Google + GitHub SSO on frontend |
| python-jose | JWT signing / verification |
| passlib + bcrypt | Password hashing |
| pyotp | TOTP generation / verification (2FA) |
| Stripe SDK | Subscription billing + refunds |
| text-embedding-3-small (OpenAI) | Master resume + JD embeddings |
| Resend | Transactional email |
| zxcvbn | Password strength scoring |

(Hirebase, Apify, AWS Lambda, AWS SQS, AWS EventBridge ship in Release Phase 3 — see §18.10.)

#### Monthly infrastructure cost summary

| Item | Release Phase 2 launch | Release Phase 3 at scale |
|---|---|---|
| AWS App Runner (backend) | $25 | $50 |
| AWS Amplify (frontend) | $5 | $10 |
| RDS PostgreSQL t3.micro | $15 | $30 |
| ElastiCache Redis t3.micro | $15 | $15 |
| CloudFront CDN | $2 | $5 |
| Lambda + SQS + EventBridge (Phase 3) | — | $10 |
| Hirebase (Phase 3) | — | $79 |
| Apify background cache (Phase 3) | — | $45 |
| Resend (transactional email) | $0 (free 3k / mo) | $20 (50k / mo) |
| Sentry | $0 (free tier) | $26 |
| **Total** | **~$62 / month** | **~$290 / month** |

---

### 18.13 Feature Dependency Map & Build Order

```
18.2 Auth (mandatory first)
  └─ required by → 18.3 Subscriptions
  └─ required by → 18.4 Master Resume
       └─ required by → 18.8 Job Fit
       └─ required by → 18.10 Job Search (resume-based matching)
       └─ enables    → 18.5 Rewrite Enhancements (Pull from master)

18.3 Subscriptions
  └─ required by → 18.8 Job Fit (subscription gate)
  └─ required by → 18.10 Job Search (subscription gate)
  └─ required by → 18.11 Cover Letter add-on

18.5 Rewrite Enhancements
  └─ requires → 18.7 ATS Guidance (Recalculate triggers Phase 4)

18.6 Free Navigation
  └─ independent; can ship alongside 18.5

18.7 ATS Guidance
  └─ requires → Phase 4 prompt extension (no new infra)

18.10 Job Search (Release Phase 3)
  └─ requires → 18.3 Subscriptions (gate)
  └─ requires → 18.4 Master Resume (resume-based matching)
  └─ requires → Hirebase API + Apify background worker
  └─ requires → 19.5 Notifications (saved-search alerts)

18.11 Cover Letter
  └─ requires → 18.4 Master Resume + completed Agent Phase 3
```

#### Recommended build order — Release Phase 2

| Step | Area | Deliverable |
|---|---|---|
| 1 | Repo | Add `LICENSE` (BSL 1.1), `COMMERCIAL.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md` |
| 2 | Infra | Add `pgvector/pgvector:pg16` to docker-compose; init Alembic |
| 3 | Backend | User model, register / login / SSO, JWT + refresh token rotation middleware |
| 4 | Backend | Email verification, password reset, optional TOTP 2FA, AuthAuditLog |
| 5 | Frontend | NextAuth.js, `/auth` page, auth guard on all protected routes |
| 6 | Backend | Subscription + CreditTransaction + RefundRecord models; Stripe checkout / portal / webhook; period counter + quota middleware |
| 7 | Frontend | `/billing` page — plan selector, upgrade / downgrade, billing portal, credit display in header |
| 8 | Backend | MasterResume + chunk models, embedding pipeline, profile routes |
| 9 | Frontend | `/profile` page — upload / paste, chunk preview, inline edit, cost preview |
| 10 | Backend | Agent Phase 3 vector selection — pull chunks by cosine similarity, per-section caps |
| 11 | Frontend | Phase 3 "Add Section" (pull from master + manual), Recalculate button, ATS badge, undo / redo |
| 12 | Frontend | Free navigation between Phases 2–4 with stale banners |
| 13 | Backend | Extended `QAOutput`; ATS Guidance generated inside Phase 4 prompt |
| 14 | Frontend | ATS Guidance panel on Phase 3 and Phase 4 with quick wins + trend sparkline |
| 15 | Backend | Cover letter route + DOCX / PDF export reuse |
| 16 | Frontend | Cover letter UI on Phase 4 + standalone `/cover-letter/new` |
| 17 | Backend | Job Fit route (`/api/fit/analyze`) using pgvector + Gemini |
| 18 | Frontend | `/fit` page — paste / upload / URL, fit score gauge, match breakdown, suggested edits |
| 19 | Backend | LLM upgrade add-on — model routing by user preference per session |
| 20 | Frontend | LLM upgrade selector on Phase 3 with pricing display tied to `LLMConfig` |

#### Recommended build order — Release Phase 3 (Job Search)

| Step | Area | Deliverable |
|---|---|---|
| 21 | Infra | AWS Lambda (EventBridge schedule) + SQS for Apify cache; alert dispatcher cron |
| 22 | Backend | JobCache + JobSearchLog + SavedSearch models; dedup + normalization pipeline |
| 23 | Backend | Hirebase search route with circuit breaker; Apify cache population |
| 24 | Backend | Saved-search + alert dispatcher Lambda integration |
| 25 | Frontend | `/jobs` page — search, results, Check Fit, Tailor Resume, Save |
| 26 | Frontend | Saved searches + alerts + blocked companies UI under `/jobs/preferences` |

---

*Release Phase 2 target: 2026 Q3*
*Release Phase 3 (Job Search) target: 2026 Q4*

---

## 19. Roadmap — Release Phase 4

> Builds on Release Phase 2 (§18.1–18.9 + 18.11–18.13) and Release Phase 3 (§18.10). Nothing in §19 affects the current implementation.

---

### 19.1 Goals

- Give users a persistent home base for everything they have built, applied for, and saved
- Give admins full control over pricing, plans, LLM assignments, feature flags, announcements, and user accounts — **no hardcoded values anywhere in the codebase**
- Support data portability and compliance: users can download or delete all their data at any time (GDPR / CCPA-aligned — §19.9)
- Deliver reminders and alerts via email, in-app, optional web push, and opt-in SMS
- Surface product analytics that admins use to make pricing and feature decisions

---

### 19.2 Data Retention Policy

| User state | Built resumes / ATS / app history | Master resume | Account record |
|---|---|---|---|
| **Active subscriber** | Kept | Kept | Kept |
| **Cancelled, within billing period** | Kept | Kept | Kept |
| **Cancelled, post-period (non-subscriber)** | Retained 30 days, then deleted | Kept indefinitely while account exists | Kept |
| **Suspended (admin / abuse)** | Kept; access blocked | Kept | Kept; cannot log in |
| **Closure requested** | Kept 30-day grace; hard-deleted on day 30 | Kept 30-day grace; hard-deleted on day 30 | Hard-deleted on day 30 |
| **Closure cancelled within grace** | Fully restored | Fully restored | Fully restored |

Notifications fire at closure request, day 23 ("7 days until deletion"), and day 30 (deletion complete).

Users can download all their data before cancellation or closure as a single ZIP (§19.6). Encrypted backups retain deleted user data for **30 additional days** for disaster recovery only — they are inaccessible to live systems and auto-purged.

Legal basis details: §19.9.

---

### 19.3 User Dashboard (`/dashboard`)

**Goal:** Single page showing everything the user has built, applied for, and saved.

#### Layout

| Section | Content |
|---|---|
| **Header** | Display name, tier badge, credits remaining (free) or next billing date (paid), notification bell |
| **Quick actions** | "New tailored resume", "Search jobs", "Edit master resume", "Generate cover letter" |
| **Subscription status** | Current plan + cycle, period usage (resumes / searches), trial status, upgrade / cancel / pause CTAs |
| **Resume history** | Paginated list of built resumes — latest version per `(job_title, company)` pair |
| **Application tracker** | Active applications grouped by stage with reminder badges |
| **ATS score history** | Sparkline trend across last 30 days; click to expand per-resume |
| **Saved jobs** | Bookmarked jobs from `/jobs` (Release Phase 3) |
| **Saved searches** | With alert status and last-run time (Release Phase 3) |
| **Recent activity** | Feed of builds, recalcs, applications, payments, notifications |

#### Resume history card

Each resume shows:

- Job title + company
- Date built
- ATS score (latest) + delta vs starting score
- Status badge (draft / applied / interviewing / offer / rejected)
- Tags (user-defined free text)
- Actions: Open, Duplicate (creates a new session pre-filled with same JD + tailored output), Download (PDF / DOCX / TXT / All ZIP), Delete

#### Filters, search, sort, bulk

- Search box (matches job title, company, tags)
- Filter chips: Status, Date range, ATS score range, Tag
- Sort: Date (default), ATS score, Company
- Bulk actions: Delete, Tag, Export

#### New backend models

```python
ResumeRecord(
    id: UUID,
    user_id: UUID,
    session_id: str,                # links to Redis session / phase outputs
    jd_title: str,
    jd_company: str,
    jd_text_hash: str,              # SHA-256(JD) for dedup
    tags: list[str],
    current_ats_score: int,
    starting_ats_score: int,        # first Phase 4 score, for delta
    status: Literal["draft", "applied", "interviewing", "offer", "rejected", "withdrawn"],
    deleted_at: datetime | None,
    created_at: datetime,
    updated_at: datetime,
)

AtsScoreHistory(
    id: UUID,
    resume_record_id: UUID,
    score: int,
    recalc_type: Literal["initial", "manual", "auto"],
    triggered_at: datetime,
)
```

#### New routes

```
GET  /api/dashboard/summary                — subscription + counts + recent activity
GET  /api/resumes                          — paginated; filters: status, tag, q, date_range
GET  /api/resumes/{id}                     — full detail + score history + linked application
PATCH /api/resumes/{id}                    — update tags, status (when no Application linked)
DELETE /api/resumes/{id}                   — soft delete (purged after 30 days)
POST /api/resumes/{id}/duplicate           — create new session pre-filled
GET  /api/resumes/{id}/download?format=pdf|docx|txt|zip
GET  /api/resumes/{id}/scores              — score history
POST /api/resumes/bulk                     — bulk action: delete | tag | export
```

---

### 19.4 Application Tracker

**Goal:** Track the full lifecycle of every job application linked to a built resume, including multi-round interviews, offer details, and rejection reasons.

#### Pipeline

```
Draft → Applied → Interviewing → Offer → Accepted
                              ↘ Rejected   (from any stage after Draft)
                              ↘ Withdrawn  (from any stage)
```

#### Multi-round interview support

Each application has zero or more `InterviewRound` rows (e.g. phone screen, take-home, onsite, final). Each round has its own date, format, interviewers, notes, and outcome.

#### Offer details

When `status` moves to `Offer`, the user records structured details: base salary, bonus, equity, sign-on, location / remote, start date, response deadline, decision.

#### Rejection / withdrawal reason

Moving to `Rejected` or `Withdrawn` captures a categorical reason plus optional notes — surfaced in admin reports.

#### Tracking fields per application

| Field | Type | Description |
|---|---|---|
| status | enum | Current pipeline stage |
| applied_date | datetime | When user marked as applied |
| follow_up_date | datetime | User-set reminder |
| notes | text | Free-text notes |
| contact_name | str | Recruiter / hiring manager |
| contact_email | str | Optional |
| job_url | str | Direct link to the job posting |
| rejection_reason | enum | `ghosted | explicit_rejection | position_filled | withdrew | other` |
| rejection_notes | text | Optional free text |

#### Reminders & alerts

| Trigger | Notification |
|---|---|
| `follow_up_date` reached | "Time to follow up on your application at {company}" |
| Next interview T-24 h | "Your interview at {company} is tomorrow at {time}" |
| Next interview T-1 h | "Your interview at {company} starts in 1 hour" |
| 14 days idle in Applied | "Any updates on your application at {company}?" |
| Status → Offer | "Congratulations! Log your offer details for {company}" |
| Offer response deadline T-48 h | "Your offer from {company} expires in 2 days" |

#### Timeline view

A vertical timeline on the application detail page shows every status change, interview round, note, attachment, and reminder. Searchable and filterable.

#### Attachments

Up to **5 attachments per application** (offer letter PDF, take-home submission, etc.). Stored in S3 with 5 MB / file and 25 MB total per application. Auto-deleted with the application record.

#### New backend models

```python
Application(
    id: UUID,
    user_id: UUID,
    resume_record_id: UUID,
    status: Literal["draft", "applied", "interviewing", "offer", "accepted", "rejected", "withdrawn"],
    applied_date: datetime | None,
    follow_up_date: datetime | None,
    notes: str | None,
    contact_name: str | None,
    contact_email: str | None,
    job_url: str | None,
    rejection_reason: str | None,
    rejection_notes: str | None,
    created_at: datetime,
    updated_at: datetime,
)

InterviewRound(
    id: UUID,
    application_id: UUID,
    round_number: int,
    name: str,                            # e.g. "Phone Screen", "Technical Onsite"
    format: Literal["phone", "video", "onsite", "take_home", "other"],
    scheduled_at: datetime | None,
    duration_minutes: int | None,
    interviewers: list[str],
    notes: str | None,
    outcome: Literal["pending", "passed", "failed", "no_show"] | None,
    created_at: datetime,
)

OfferDetail(
    id: UUID,
    application_id: UUID,
    base_salary_usd: int | None,
    bonus_usd: int | None,
    equity_description: str | None,
    sign_on_usd: int | None,
    benefits: str | None,
    location: str | None,
    remote: bool,
    start_date: date | None,
    response_deadline: datetime | None,
    decision: Literal["pending", "accepted", "declined"] | None,
    decision_notes: str | None,
    created_at: datetime,
)

ApplicationAttachment(
    id: UUID,
    application_id: UUID,
    filename: str,
    content_type: str,
    size_bytes: int,
    s3_key: str,
    uploaded_at: datetime,
)
```

#### New routes

```
POST /api/applications                              — create application linked to resume
GET  /api/applications                              — list; filters: status, company, date
GET  /api/applications/{id}                         — full detail + rounds + offer + attachments + timeline
PATCH /api/applications/{id}                        — update status, dates, notes
DELETE /api/applications/{id}                       — delete

POST /api/applications/{id}/rounds                  — add interview round
PATCH /api/applications/{id}/rounds/{rid}           — update
DELETE /api/applications/{id}/rounds/{rid}          — remove

POST /api/applications/{id}/offer                   — set offer details
PATCH /api/applications/{id}/offer                  — update

POST /api/applications/{id}/attachments             — upload (multipart)
DELETE /api/applications/{id}/attachments/{aid}     — delete

GET  /api/applications/{id}/reminders               — list scheduled reminders
POST /api/applications/{id}/reminders               — set custom reminder
DELETE /api/applications/{id}/reminders/{rid}       — cancel
```

---

### 19.5 Notifications

**Providers:** Resend for transactional email (free up to 3,000 / month; upgrade to AWS SES at scale). Web push via VAPID. SMS via Twilio for opt-in interview alerts only.

#### Channels

| Channel | When |
|---|---|
| **In-app** | Always; bell icon in header with unread count |
| **Email** | User-configurable per category; defaults on for security / billing / interview / offer |
| **Web push** | Opt-in only; single prompt on first dashboard visit; off by default |
| **SMS** | Opt-in only; **interview reminders only**; requires phone verification |

#### Notification categories

| Category | Default channels | Trigger |
|---|---|---|
| Account security | email + in-app | New device login, password change, 2FA enrollment, suspicious login |
| Email verification | email | Registration; resend |
| Payment | email + in-app | Failure, success, refund, trial ending |
| Subscription | email + in-app | Cancellation, renewal, expiry warning T-3 days, pause / resume |
| Resume | in-app | Build complete, export ready, recalculation done |
| Application — follow-up | email + in-app | `follow_up_date` reached |
| Application — interview | email + in-app + web push + SMS (if opted in) | T-24 h, T-1 h |
| Application — nudge | in-app | 14 days idle |
| Application — offer | email + in-app | Status → Offer; deadline T-48 h |
| Job alerts | email | Saved-search frequency (daily / weekly) |
| Data export | email + in-app | Export ZIP ready (download link valid 24 h) |
| Account closure | email | Request, day 23 warning, deletion complete |
| Admin announcement | in-app | Admin-published banner (§19.7) |

#### Digest mode

Users can opt into a **daily digest** for non-urgent categories (Application nudge, Job alerts). Replaces individual emails with one batched email per day.

#### Email contents

- Branded HTML + plain-text fallback (Resend templates)
- Unsubscribe link in every email; per-category honored via `NotificationPreference`
- One-click deep link "View in app"

#### Models

```python
Notification(
    id: UUID,
    user_id: UUID,
    type: str,                            # e.g. "interview_reminder_24h"
    category: str,                        # see categories above
    channel: Literal["email", "in_app", "web_push", "sms", "multi"],
    title: str,
    body: str,                            # HTML (email) / plaintext (in-app, push, SMS)
    data: JSON,                           # deep-link targets, application_id, etc.
    read_at: datetime | None,
    scheduled_at: datetime,
    sent_at: datetime | None,
    delivery_status: Literal["pending", "sent", "delivered", "bounced", "failed"],
    error: str | None,
    created_at: datetime,
)

NotificationPreference(
    id: UUID,
    user_id: UUID,                        # unique
    email_enabled_categories: list[str],
    in_app_enabled_categories: list[str],
    web_push_enabled: bool,
    web_push_subscription: JSON | None,   # browser push endpoint + keys
    sms_enabled: bool,
    sms_phone: str | None,                # E.164; verified
    sms_phone_verified_at: datetime | None,
    digest_mode: Literal["off", "daily"],
    updated_at: datetime,
)
```

#### Routes

```
GET  /api/notifications                       — list; filters: unread, category
GET  /api/notifications/unread-count          — header badge
PATCH /api/notifications/{id}/read            — mark read
PATCH /api/notifications/read-all             — mark all read
DELETE /api/notifications/{id}                — dismiss

GET  /api/notifications/preferences           — current prefs
PATCH /api/notifications/preferences          — update prefs

POST /api/notifications/web-push/subscribe    — register browser push subscription
DELETE /api/notifications/web-push/subscribe  — unregister

POST /api/notifications/sms/send-verification — start phone verification
POST /api/notifications/sms/verify            — confirm code
```

#### Environment variables

```
RESEND_API_KEY=
RESEND_FROM_EMAIL=noreply@zanganehai.com
WEB_PUSH_VAPID_PUBLIC_KEY=
WEB_PUSH_VAPID_PRIVATE_KEY=
WEB_PUSH_CONTACT=mailto:support@zanganehai.com
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
```

#### Delivery & scheduling

- Scheduled notifications routed through AWS EventBridge → Lambda dispatcher → Resend / Twilio / web push
- Failed deliveries retry with exponential backoff (3 attempts)
- Bounced email addresses are auto-suppressed (Resend webhook → set `User.email_bounced_at`); the user sees a banner asking to update their email

---

### 19.6 Data Export & Account Closure

#### Export flow

```
User clicks "Download my data" on /dashboard/settings
  → POST /api/account/export
  → Background job assembles ZIP:
       ├─ resumes/{slug}/resume.{pdf,docx,txt}
       ├─ cover_letters/{slug}/cover_letter.{pdf,docx,txt}
       ├─ applications.csv             (status, dates, contacts, notes)
       ├─ interview_rounds.csv
       ├─ offers.csv
       ├─ ats_scores.csv
       ├─ saved_jobs.csv
       ├─ saved_searches.csv
       ├─ master_resume.{pdf,docx,txt}
       ├─ notifications_archive.csv
       └─ account_info.json            (email, tier, created_at, preferences, audit summary)
  → Upload ZIP to S3 with 24-h-TTL presigned URL
  → "Download ready" notification (email + in-app)
  → User downloads ZIP
```

Rate-limited to **2 exports per 24 hours per user**.

#### Account closure flow (30-day grace)

```
User clicks "Close my account" on /dashboard/settings/danger
  → Confirm dialog: "Download your data first?"
       ├─ YES → trigger export → user confirms download → proceed
       └─ NO  → require typing "DELETE" to confirm
  → POST /api/account/close
  → If active subscription:
       ├─ Cancel at period end (default; keeps paid time), OR
       └─ Cancel immediately with no refund (user choice)
  → Mark User.closure_requested_at = now()
  → Schedule hard deletion at now() + 30 days
  → Send "Account closure scheduled" email

Day 23 → "7 days until deletion" reminder
Day 30 → Hard-delete all user rows + S3 objects; send "Account deleted" email

User can cancel closure any time before day 30:
  → POST /api/account/close/cancel
  → Clear closure_requested_at; full access restored
```

This resolves the previous ambiguity between §19.2's "Nothing — full deletion on request" and the grace period: closure is **always** a 30-day grace unless the user separately invokes `/api/account/delete-immediately` (which is super-admin-only via §19.7).

#### Routes

```
POST /api/account/export                 — trigger ZIP export; returns job_id
GET  /api/account/export/{id}            — check status; returns presigned URL when ready
GET  /api/account/exports                — list past exports (last 30 days)

POST /api/account/close                  — initiate closure (30-day grace)
POST /api/account/close/cancel           — cancel pending closure
DELETE /api/account                      — internal; called by scheduler after 30 days

POST /api/account/delete-immediately     — emergency hard delete; super-admin only (via §19.7)
```

---

### 19.7 Admin Panel (`/admin`)

**Goal:** Full control over pricing, plans, LLM assignments, feature flags, announcements, user accounts, refunds, and reports — **no hardcoded values anywhere in the codebase**.

Admins authenticate through a separate `/admin/auth` flow. **2FA is mandatory.** Admin sessions are **1-hour TTL** (no sliding renewal) and bound to the originating IP. The first super-admin is seeded from `BOOTSTRAP_SUPER_ADMIN_EMAIL` at first deploy; subsequent admins are created from the panel and receive an invite email.

#### Admin roles

| Role | Permissions |
|---|---|
| **super-admin** | Full access — pricing, plans, LLM config, feature flags, announcements, user management (incl. suspend), refunds, credit grants, all reports |
| **support-agent** | View users, view / edit credits (with reason), view subscriptions, trigger user exports / closures on behalf, process refunds within the self-service window |
| **read-only-analyst** | Read-only reports + LLM cost dashboards; **no user PII** beyond aggregate counts |

#### Admin panel sections

**1. Pricing & Plans**

- Edit subscription prices and limits (Daily / Weekly / Monthly with recurring or yearly cycle)
- Edit LLM upgrade prices (Better pack, Better monthly / yearly, Best per-resume, Best monthly / yearly)
- Edit free registration credit grant (default 6)
- Toggle 7-day free trial per Stripe price ID
- Effective date: apply to new subscribers only OR apply to all on next renewal — admin chooses per change
- Every change written to `AdminAuditLog` with diff and is reflected in the public price API at `/api/billing/prices`

**2. LLM Configuration**

- Assign provider + model string + cost-per-resume for each tier (Standard / Better / Best)
- Configure a fallback model per tier (used if primary returns 5xx 3 consecutive times)
- Configure model per agent phase (Standard tier only; Better / Best always apply to Phase 3)
- Vector similarity threshold for Master Resume chunk selection (default 0.72)
- Toggle BYOK-only mode if needed

**3. Feature Flags**

- Boolean toggles per feature: `job_search_enabled`, `cover_letter_enabled`, `master_resume_enabled`, `2fa_required_for_users`, etc.
- Targeting: all users, percentage rollout (0–100), email allowlist, email blocklist
- Resolved via `/api/feature-flags` for the current user; cached client-side for 30 s

**4. Announcements**

- Schedule a global banner (info / warning / maintenance) with start + end time
- Optional CTA label + URL
- Rendered in-app for all matching users during the active window
- Per-user dismiss is persisted

**5. User Management**

- Search by email, ID, Stripe customer ID
- View user profile: tier, credits, subscription, resume count, suspension status, BYOK fingerprint
- Edit credit balance (super-admin + support-agent; reason required → logged)
- Manually grant or revoke subscription (super-admin only)
- View full credit transaction history
- Trigger data export on behalf of user
- Initiate account closure on behalf of user
- **Suspend / unsuspend** user (super-admin only) — sets `User.suspended_at`; blocks login
- View login history (last 50 entries) from `AuthAuditLog`

**6. Refunds**

- Pending refund requests queue (from `POST /api/subscriptions/refund-request`)
- Per-request: approve (super-admin) → Stripe refund + `RefundRecord` + credit reversal; deny with reason → user email; chargeback auto-flag with suspended user

**7. Reports**

All reports are filterable by date range and exportable to CSV.

- Daily / weekly / monthly active users (DAU / WAU / MAU)
- New registrations + activation funnel (registered → email-verified → first build → first export → subscribed)
- Subscription conversion rate (free → paid; tier mix)
- Revenue by plan + LLM add-on
- LLM cost vs revenue margin (live, computed from `LLMConfig.cost_per_resume_usd` × volume)
- Churn rate by plan
- Top searched job titles (Release Phase 3, from `JobSearchLog`)
- Rejection reasons distribution (from `Application.rejection_reason`)
- Feature flag exposure analytics

**8. System Health**

- Read-only view: Stripe webhook delivery success, Hirebase circuit breaker state, Apify queue depth, Resend delivery success rate, error rate (last 24 h), p50 / p95 / p99 LLM latency per tier

#### New backend models

```python
AdminUser(
    id: UUID,
    email: str,                          # unique
    display_name: str,
    role: Literal["super-admin", "support-agent", "read-only-analyst"],
    password_hash: str,                  # bcrypt
    totp_secret: bytes,                  # AES-256-GCM encrypted; 2FA mandatory
    totp_recovery_codes: list[str],      # SHA-256 hashed
    suspended_at: datetime | None,
    created_by: UUID | None,             # null for bootstrap admin
    created_at: datetime,
    last_login_at: datetime,
    last_login_ip: str,
)

PlanConfig(
    id: UUID,
    plan: Literal["daily", "weekly", "monthly"],
    billing_cycle: Literal["recurring", "yearly"],
    price_usd: float,
    resume_limit: int,
    search_limit: int,
    stripe_price_id: str,
    trial_days: int,                     # 0 = no trial
    effective_from: datetime,
    apply_to_existing: bool,
    superseded_by: UUID | None,          # links to next config version
    created_by: UUID,
    created_at: datetime,
)

LLMConfig(
    id: UUID,
    tier: Literal["standard", "better", "best"],
    provider: str,
    model_string: str,
    fallback_provider: str | None,
    fallback_model_string: str | None,
    cost_per_resume_usd: float,
    phases_enabled: list[Literal["1","2","3","4","fit","cover_letter"]],
    active: bool,
    created_by: UUID,
    created_at: datetime,
)

FeatureFlag(
    id: UUID,
    key: str,                            # e.g. "job_search_enabled"
    description: str,
    enabled: bool,
    rollout_percent: int,                # 0–100
    allowlist_emails: list[str],
    blocklist_emails: list[str],
    updated_by: UUID,
    updated_at: datetime,
)

Announcement(
    id: UUID,
    title: str,
    body_markdown: str,
    severity: Literal["info", "warning", "maintenance"],
    cta_label: str | None,
    cta_url: str | None,
    starts_at: datetime,
    ends_at: datetime,
    created_by: UUID,
    created_at: datetime,
)

AdminAuditLog(
    id: UUID,
    admin_id: UUID,
    action: str,                         # "price_change", "credit_edit", "user_suspend", ...
    target_type: str,
    target_id: str,
    old_value: JSON | None,
    new_value: JSON | None,
    request_ip: str,
    created_at: datetime,
)

AuthAuditLog(                            # user-side; surfaced to admin
    id: UUID,
    user_id: UUID | None,
    event: Literal[
        "login_success", "login_failure", "logout", "password_reset",
        "2fa_enroll", "2fa_disable", "suspicious_login", "account_locked",
    ],
    ip: str,
    user_agent: str,
    metadata: JSON,
    created_at: datetime,
)
```

#### New admin routes

```
# Auth
POST /api/admin/auth/login                  — admin login (separate from user auth)
POST /api/admin/auth/2fa/verify             — TOTP step (required)
POST /api/admin/auth/logout
POST /api/admin/auth/invite                 — super-admin creates a new admin (sends email)
POST /api/admin/auth/accept-invite          — invited admin sets password + enrolls 2FA

# Plans & Pricing
GET  /api/admin/plans                       — current + future plan configs
POST /api/admin/plans                       — create new plan config
PATCH /api/admin/plans/{id}                 — edit a not-yet-effective config
GET  /api/admin/plans/history               — change history

# LLM Config
GET  /api/admin/llm                         — current LLM configs per tier
POST /api/admin/llm                         — update / replace model for a tier
GET  /api/admin/llm/history                 — change history

# Feature Flags
GET  /api/admin/feature-flags
POST /api/admin/feature-flags
PATCH /api/admin/feature-flags/{key}
DELETE /api/admin/feature-flags/{key}

# Announcements
GET  /api/admin/announcements
POST /api/admin/announcements
PATCH /api/admin/announcements/{id}
DELETE /api/admin/announcements/{id}

# Users
GET  /api/admin/users                       — paginated list with search
GET  /api/admin/users/{id}                  — full detail
PATCH /api/admin/users/{id}/credits         — adjust credit balance (reason required)
PATCH /api/admin/users/{id}/subscription    — manually grant / revoke subscription
PATCH /api/admin/users/{id}/suspend         — suspend / unsuspend
GET  /api/admin/users/{id}/transactions     — credit transaction history
GET  /api/admin/users/{id}/auth-log         — login history
POST /api/admin/users/{id}/export           — trigger data export
POST /api/admin/users/{id}/close            — initiate account closure
POST /api/admin/users/{id}/delete-immediately — super-admin only emergency delete

# Refunds
GET  /api/admin/refunds                     — pending + history
POST /api/admin/refunds/{id}/approve        — approve & dispatch Stripe refund
POST /api/admin/refunds/{id}/deny           — deny with reason

# Reports
GET  /api/admin/reports/overview
GET  /api/admin/reports/registrations
GET  /api/admin/reports/revenue
GET  /api/admin/reports/llm-costs
GET  /api/admin/reports/churn
GET  /api/admin/reports/job-searches        — Release Phase 3
GET  /api/admin/reports/applications        — rejection reasons, status mix
GET  /api/admin/reports/feature-flags
GET  /api/admin/reports/system-health

# Audit logs
GET  /api/admin/audit-log
GET  /api/admin/auth-log
```

#### Public feature-flag endpoint (used by the frontend)

```
GET  /api/feature-flags                     — flags resolved for the current user (cached 30s)
GET  /api/billing/prices                    — public price list reflecting current PlanConfig + LLMConfig
GET  /api/announcements                     — active announcements for the current user
```

---

### 19.8 Cancellation, Pause & Downgrade

| Action | Behaviour |
|---|---|
| **Cancel** | Self-service from `/dashboard/billing` (or by support-agent). Subscription stays active until `period_end`; data retention per §19.2. |
| **Pause** | Available on Monthly + Yearly cycles only. Pauses billing for up to **90 days**. While paused: no resume runs, no searches, no recalcs; data retained. Resumes automatically at the end of the pause or earlier via "Resume now". |
| **Downgrade** | Effective at next renewal. No proration. |
| **Upgrade** | Immediate; Stripe pro-rates the difference. |
| **Refunds** | See §18.3 refund policy. |

Yearly subscribers who cancel keep access for the remainder of their annual period. There are no partial refunds outside the §18.3 windows unless authorized by a super-admin.

New routes:

```
POST /api/subscriptions/pause       — start pause (max 90 days)
POST /api/subscriptions/unpause     — end pause early
```

---

### 19.9 GDPR & CCPA Compliance

- **Lawful basis (GDPR Art. 6):** performance of contract (subscription / resume building); consent (marketing emails); legitimate interest (security audit logs)
- **Right of access:** `/api/account/export` (§19.6)
- **Right to erasure:** `/api/account/close` (§19.6); 30-day grace; backups purged within 60 days of grace expiry
- **Right to rectification:** `/api/profile/resume` + `/api/auth/me` PATCH for display name / email
- **Right to data portability:** the export ZIP includes machine-readable CSV + JSON
- **Right to object / restrict processing:** Pause subscription (§19.8); opt-out of marketing
- **CCPA "Do Not Sell My Personal Information":** we do not sell user data; the footer link leads to a confirmation page documenting this
- **DPO contact:** `privacy@zanganehai.com`; response SLA 30 days
- **Sub-processor list:** published at `/legal/sub-processors` and updated with 30-day notice on changes
- **Children:** service is not directed at users under 16; registration requires a self-attestation checkbox

#### Audit-log retention

| Log | Retention |
|---|---|
| `AdminAuditLog` | 7 years (financial / compliance) |
| `AuthAuditLog` | 1 year |
| `Notification` (sent) | 90 days hot, then archived 1 year |
| `JobSearchLog` | 1 year |
| Application logs (structlog) | 30 days hot in CloudWatch; 1 year cold in S3 |

---

### 19.10 Feature Dependency Map

```
19.3 User Dashboard
  └─ requires → 18.2 Auth
  └─ requires → 18.3 Subscriptions
  └─ requires → Agent Phase 3 / 4 session outputs → ResumeRecord

19.4 Application Tracker
  └─ requires → 19.3 Dashboard (ResumeRecord)
  └─ requires → 19.5 Notifications (reminders)
  └─ requires → AWS S3 (attachments)

19.5 Notifications
  └─ requires → 18.2 Auth (user email + phone)
  └─ requires → Resend, Twilio (opt-in), Web Push (browser)
  └─ requires → AWS EventBridge + Lambda dispatcher

19.6 Data Export & Closure
  └─ requires → 19.3 Dashboard (resume records)
  └─ requires → 19.4 Tracker (application history)
  └─ requires → 18.4 Master Resume
  └─ requires → AWS S3 (ZIP storage)

19.7 Admin Panel
  └─ requires → 18.2 Auth (separate admin auth + mandatory 2FA)
  └─ requires → 18.3 Subscriptions (plan config)
  └─ requires → 19.3 Dashboard (user management)
  └─ requires → 19.5 Notifications (admin email + invite)

19.8 Pause / Downgrade
  └─ requires → 18.3 Subscriptions

19.9 GDPR / CCPA
  └─ requires → 19.6 Export + Closure
```

#### Recommended build order — Release Phase 4

| Step | Area | Deliverable |
|---|---|---|
| 27 | Backend | ResumeRecord + AtsScoreHistory models; link session outputs to user |
| 28 | Frontend | `/dashboard` page — subscription, resume history, ATS trend, saved jobs, recent activity |
| 29 | Backend | Application + InterviewRound + OfferDetail + ApplicationAttachment models + routes |
| 30 | Frontend | Application tracker — pipeline, timeline, multi-round, offer details, attachments |
| 31 | Backend | Notification + NotificationPreference models; Resend + Twilio + web-push integration; EventBridge scheduler |
| 32 | Frontend | In-app notification bell + preferences page + web-push opt-in + SMS verification + digest opt-in |
| 33 | Backend | Data-export ZIP builder + S3 + 30-day closure-grace flow |
| 34 | Frontend | Export + closure UX (`/dashboard/settings/danger`) + reactivation flow |
| 35 | Backend | AdminUser + PlanConfig + LLMConfig + FeatureFlag + Announcement + AdminAuditLog + AuthAuditLog models; all admin routes; mandatory 2FA; bootstrap admin |
| 36 | Frontend | `/admin` panel — pricing, LLM config, feature flags, announcements, users, refunds, reports, system health |
| 37 | Backend | Pause / downgrade flows; refund workflow integration |
| 38 | Compliance | `/legal` static pages (Terms, Privacy, Sub-processors), DPO mailbox routing, CCPA confirmation page |

---

### 19.11 New Technology Additions (Release Phase 4)

| Addition | Purpose |
|---|---|
| Resend SDK | Transactional email (verification, reminders, alerts, exports, admin invites) |
| Twilio SDK | Opt-in SMS for interview reminders |
| `pywebpush` | Web push delivery (VAPID) |
| AWS S3 | ZIP export storage + application attachments |
| AWS EventBridge + Lambda | Scheduled reminder + closure-grace jobs |
| Custom Next.js admin panel (preferred over `react-admin`) | Admin UI; shares design system with main app |
| `recharts` | Dashboard + admin charts |

---

*Release Phase 2 target: 2026 Q3*
*Release Phase 3 (Job Search) target: 2026 Q4*
*Release Phase 4 (Dashboard / Tracker / Admin) target: 2027 Q1*
*Last updated: 2026-05-30*
