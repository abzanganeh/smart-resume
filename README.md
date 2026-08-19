

<p align="center">
  <img src="docs/assets/marketing/smart-resume-photo-03.png" alt="Flint Resume — AI tailoring and company intel" width="720" />
</p>

# Smart Resume Agent

An AI-powered job-search platform. Build your master resume by speaking or uploading, tailor it to any job description in minutes, find matching jobs, write cover letters, and track every application — all in one place.

---

## Quick Start

### Docker Compose (recommended)

```bash
cp backend/.env.example backend/.env
# Fill in at minimum: NEXTAUTH_SECRET, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GEMINI_API_KEY
docker compose up
```

**Staging deploy:** see [STAGING.md](./STAGING.md) for env checklist, OAuth setup, Stripe webhook, and manual smoke gates.

| Service   | URL                          |
|-----------|------------------------------|
| App       | http://localhost:3000        |
| API       | http://localhost:8000        |
| API docs  | http://localhost:8000/docs   |

### Local development

**Backend** (Python 3.12+, [uv](https://github.com/astral-sh/uv)):
```bash
cd backend
cp .env.example .env   # fill in required vars
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

**Frontend** (Node 20+, pnpm):
```bash
cd frontend
cp .env.local.example .env.local   # fill in NEXTAUTH_* vars
pnpm install
pnpm dev
```

---

## How It Works

### 1 — Sign in

Sign in with Google (or any configured OAuth provider). Your account links your master resume, sessions, applications, and usage quota.

### 2 — Build your master resume

Go to **Profile** and choose one of three methods:

| Method | How |
|--------|-----|
| **Upload** | PDF, DOCX, or plain text — parsed and chunked into your master resume |
| **Tell your story** | Record up to 30 × 60-second voice segments. Talk naturally. Optionally tap **"Coach me ✨"** after any segment — the AI asks one follow-up question to draw out missing metrics or outcomes. |
| **Coached interview** | The AI asks up to 15 structured career questions (roles, achievements, leadership, skills, education) and follows up when answers are vague. Answer by typing or speaking. Costs 1 credit per session; free for subscribers. |

All three paths produce the same output: a semantic master resume stored as embedded chunks in Postgres. Tailored resumes always draw from this store — so rewrites use your real experience, not hallucinations.

### 3 — Start a session

Paste or upload your resume and the job description on the **New Session** page. Optionally provide a JD URL (paste text directly for JavaScript-rendered pages like Greenhouse, Lever, or Jobright).

Select your **AI model tier**:

| Tier     | Model                 | Cost               |
|----------|-----------------------|--------------------|
| Standard | Gemini 2.5 Flash-Lite | Included with plan |
| Better   | Gemini 2.5 Flash      | +$0.898 / resume   |
| Best     | Claude Sonnet 4.6     | +$2.99 / resume    |

Platform AI (Gemini) is the default for all wizard steps. Upgrade tiers bill per resume via Stripe.

### 4 — Run the four phases

Each phase has a **Run** button. Cached outputs replay automatically without re-running unless you click Re-run.

| Phase | Tab         | What it does                                                               |
|-------|-------------|----------------------------------------------------------------------------|
| 1     | Audit       | Extracts must-have and nice-to-have ATS keywords from the JD               |
| 2     | Audit       | Gaps every missing keyword, weak bullet, and cliché in your current resume |
| 3     | Rewrite     | Rewrites with exact JD phrasing; never fabricates metrics                  |
| 4     | QA & Export | 8-point quality checklist; ATS score with before/after delta               |

Re-running Phase 2 automatically marks Phase 3 and 4 outputs as stale.

### 5 — Review and iterate

**Rewrite tab:**
- Edit any section inline (Summary, Skills, Experience bullets, Education, Projects)
- **Regenerate** individual sections or bullets via AI
- **Undo / Redo** through full version history
- **Chat panel** — freeform edit requests ("add a metric to the second bullet"); AI generates a patch you accept or reject

**ATS Guidance panel (Phase 4):**
- ATS score with baseline → current delta (e.g. Baseline 60 → Now 65 ↑+5 pts)
- Score ceiling based on your master resume content
- **Quick wins** — one-click keyword and phrasing suggestions; accept and apply in bulk
- **Blocking issues** — ranked by severity

### 6 — Export & apply

- Download **PDF** or **DOCX**
- Generate a matching **Cover Letter** (one click, edit inline, export PDF)
- View your **Job Fit Score** — semantic similarity between master resume and JD before spending a credit
- Save the job to your **Application Tracker**

---

## Features

| Feature | Description |
|---------|-------------|
| **Story Mode** | Voice recording (Web Speech API — Chrome/Edge free; Whisper fallback 2 credits) with optional per-segment AI coaching |
| **Coached Interview** | AI-driven Q&A session — structured questions with follow-ups; compiles to master resume |
| **Master Resume** | Persistent semantic store; all tailored resumes draw from it |
| **ATS Optimization** | Keyword extraction, gap analysis, evidence-based rewrite, 8-point QA |
| **AI Chat** | Inline chat for freeform edits and section regeneration |
| **Cover Letter** | Generated from master resume + JD; editable; PDF export |
| **Job Search** | DB-first corpus search (500 ATS employers, tiered polling) with Hirebase gap-fill |
| **Application Tracker** | Kanban board (Applied → Interview → Offer → Closed); notes and history |
| **Job Fit Score** | Pre-tailor semantic similarity score |
| **Admin Panel** | User management, billing, feature flags, LLM config, audit log, system health |

---

## Authentication & Providers

### OAuth setup (required)

```bash
# backend/.env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
NEXTAUTH_SECRET=...          # any random 32-char string
NEXTAUTH_URL=http://localhost:3000
```

### LLM providers

The platform ships with Gemini pre-configured. To add other providers or override models:

```bash
# backend/.env — any subset is valid
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...
OPENROUTER_API_KEY=sk-or-...
```

Platform operators configure provider keys in `backend/.env`. End users run on platform AI unless an admin enables alternate routing in a future release.

### Adding a new LLM provider

1. Create `backend/app/llm/providers/my_provider_adapter.py` — implement `LLMClient`
2. Add a `case "my_provider":` block in `backend/app/llm/factory.py`
3. Add the provider entry to `backend/app/llm/model_catalog.py`

---

## Architecture

```
frontend/                    Next.js 15 (App Router, NextAuth.js, Tailwind)
  app/
    (auth, dashboard, profile, session, jobs, tracker,
     billing, cover-letter, fit, notifications, settings, admin)
  components/
    profile/                 StoryRecorder, StoryInterview, StoryModeSelector,
                             StoryCoach, StorySegment, ChunkCard, …
    session/                 ResumeChat, ATSGuidancePanel, CoverLetterPanel, …
    nav/, dashboard/, jobs/

backend/
  app/
    agent/                   Phase 1–4 agents, story_to_resume, story_coach,
                             story_interview, polish, cover_letter, chat, job_fit
    routers/                 profile, phases, resume, fit, cover_letter, jobs,
                             dashboard, tracker, billing, admin, auth, sessions
    models/                  Pydantic schemas (session, story, billing, admin, …)
    llm/                     LLM client abstraction + provider adapters
    parsers/                 PDF / DOCX / HTML → plain text
    services/
      admin_auth/            TOTP 2FA, session tokens, invite flow, audit
      billing/               Stripe webhooks, credit system, quota, refunds
      master_resume/         Chunking, embedding, CRUD
      retrieval/             Semantic retrieval with token budgeting
      notifications/         Email, push, SMS adapters
      jobs/                  Hirebase client, cache writer, circuit breaker
      export/                PDF/DOCX assembler, closure, S3 storage
      dashboard/             Activity metrics, resume record
      tracker/               Application state machine, S3 attachments

infra/
  terraform/                 AWS infrastructure (Lambda, S3, SQS, RDS)
  apify_cache_worker/        Job listing cache worker
  notification_scheduler/    Scheduled notification dispatcher
  alert_dispatcher/          System alert handler
```

Sessions are stored in Redis. Resume chunks and embeddings are in Postgres (pgvector). See `docs/SYSTEM_DESIGN_PHASE_2.md` for the full architecture, API contracts, data models, and system design sections (§1–§22).

---

## Admin Panel

The admin panel lives at `/admin/auth` and is separate from the main app login.

On first startup, if `BOOTSTRAP_SUPER_ADMIN_EMAIL` is set in `backend/.env`, a super-admin account is created automatically along with a linked app user (pro tier) so the owner can also log into the main app with the same email.

| Variable | Description |
|----------|-------------|
| `BOOTSTRAP_SUPER_ADMIN_EMAIL` | Email for the bootstrap super-admin |
| `BOOTSTRAP_SUPER_ADMIN_PASSWORD` | Initial password (must be changed on first login) |
| `BOOTSTRAP_SUPER_ADMIN_DISPLAY_NAME` | Display name |

First login requires TOTP enrollment (QR code shown) and a mandatory password change.

Admin panel pages: Dashboard · Users · Plans · **Promo & credits** · LLM Config · Feature Flags · Announcements · Refunds · Reports · Audit Log · System Health.

**Promo & credits** lets super-admins and admins set how many free credits new signups receive (default **3**, stored in active free-tier limits; existing balances are unchanged) and manage campaign coupon codes. Per-user coupons are issued from the Users drawer; users redeem codes on **Billing**.

---

## Key environment variables

| Variable                      | Required | Description                                      |
|-------------------------------|----------|--------------------------------------------------|
| `NEXTAUTH_SECRET`             | Yes      | NextAuth signing secret (min 32 chars)           |
| `NEXTAUTH_URL`                | Yes      | Public URL of the frontend                       |
| `GOOGLE_CLIENT_ID`            | Yes      | Google OAuth client ID                           |
| `GOOGLE_CLIENT_SECRET`        | Yes      | Google OAuth client secret                       |
| `DATABASE_URL`                | Yes      | Postgres connection string                       |
| `REDIS_URL`                   | Yes      | Redis connection string                          |
| `GEMINI_API_KEY`              | Yes*     | Default LLM provider key                         |
| `BOOTSTRAP_SUPER_ADMIN_EMAIL` | No       | Email that gets super-admin on first startup     |
| `OPENAI_EMBEDDING_KEY`        | No       | Enables semantic master resume embeddings        |
| `STRIPE_SECRET_KEY`           | No       | Enables subscription billing                     |
| `MAX_JD_CHARS`                | No       | Max job description length (default 20 000)      |

\* At least one LLM provider key is required.

Full variable reference: `backend/.env.example`
