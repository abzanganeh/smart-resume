# Smart Resume Agent

An AI-powered resume tailoring platform. Upload your resume, paste a job description, and the agent rewrites your resume with exact JD phrasing and ATS-optimized keywords — without fabricating metrics.

---

## Quick Start

### Docker Compose (recommended)

```bash
cp backend/.env.example backend/.env
# Fill in at minimum: NEXTAUTH_SECRET, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GEMINI_API_KEY
docker compose up
```

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

Sign in with Google (or any configured OAuth provider). Your account links uploaded resumes, sessions, and usage quota.

### 2 — Upload your master resume (optional but recommended)

Go to **Profile → Upload Resume**. The master resume is chunked and embedded — Phase 3 draws from it when rewriting to ensure your real experience is used rather than the thin text in your session resume.

### 3 — Start a session

Paste or upload your resume and the job description. Optionally provide a JD URL — if the page is JavaScript-rendered (Jobright, Greenhouse, Lever, etc.) the app will warn you to paste the text directly.

Select your **AI model tier** for the rewrite:

| Tier     | Model                    | Cost              |
|----------|--------------------------|-------------------|
| Standard | Gemini 2.5 Flash-Lite    | Included with plan |
| Better   | Gemini 2.5 Flash         | +$0.898 / resume  |
| Best     | Claude Sonnet 4.6        | +$2.99 / resume   |

### 4 — Run the four phases

Each phase has a **Run** button. Phases do not auto-trigger — cached outputs replay automatically without re-running unless you click Re-run.

| Phase | Tab         | What it does                                                                 |
|-------|-------------|------------------------------------------------------------------------------|
| 1     | Audit       | Extracts must-have and nice-to-have ATS keywords from the JD                 |
| 2     | Audit       | Gaps every missing keyword, weak bullet, and cliché in your current resume   |
| 3     | Rewrite     | Rewrites with exact JD phrasing; never fabricates metrics                    |
| 4     | QA & Export | Runs the 8-point quality checklist; computes your ATS score                  |

Re-running Phase 2 automatically marks Phase 3 and 4 outputs as stale.

### 5 — Review and iterate

**Rewrite tab:**
- Edit any section inline (Summary, Skills, Experience bullets, Education, Projects)
- **Regenerate** individual sections or bullets via the AI
- **Undo / Redo** through version history
- **Chat panel** — type a freeform edit request (e.g. "add a metric to the second bullet") and the AI generates a patch you can accept or reject without re-running the full pipeline

**ATS Guidance panel (Phase 4):**
- ATS score with baseline → current delta (e.g. Baseline 60 → Now 65 ↑+5 pts)
- Score ceiling based on your master resume content
- **Quick wins** — one-click keyword and phrasing suggestions; accept the ones you want, then apply them all at once
- **Blocking issues** — ranked by severity (high / medium)

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

Users can also supply their own key (BYOK) per session from the model picker in the UI. The key is held only in `sessionStorage` and never logged.

### Adding a new LLM provider

1. Create `backend/app/llm/providers/my_provider_adapter.py` — implement `LLMClient`
2. Add a `case "my_provider":` block in `backend/app/llm/factory.py`
3. Add the provider entry to `backend/app/llm/model_catalog.py`

---

## Architecture

```
frontend/          Next.js 15 app (App Router, NextAuth.js, Tailwind)
backend/
  app/
    agent/         Phase 1–4 LLM agents + Chat agent
    routers/       FastAPI route handlers
    models/        Pydantic schemas (session, keywords, QA, chat, …)
    llm/           LLM client abstraction + provider adapters
    parsers/       PDF / DOCX / HTML → plain text
    services/      Subscription, notifications, profile, dashboard
```

Sessions are stored in Redis. Parsed resume chunks and embeddings are stored in Postgres (pgvector). See `docs/SYSTEM_DESIGN_PHASE_2.md` for the full architecture, API contracts, and data models.

---

## Key environment variables

| Variable                   | Required | Description                                    |
|----------------------------|----------|------------------------------------------------|
| `NEXTAUTH_SECRET`          | Yes      | NextAuth signing secret (min 32 chars)         |
| `NEXTAUTH_URL`             | Yes      | Public URL of the frontend                     |
| `GOOGLE_CLIENT_ID`         | Yes      | Google OAuth client ID                         |
| `GOOGLE_CLIENT_SECRET`     | Yes      | Google OAuth client secret                     |
| `DATABASE_URL`             | Yes      | Postgres connection string                     |
| `REDIS_URL`                | Yes      | Redis connection string                        |
| `GEMINI_API_KEY`           | Yes*     | Default LLM provider key                       |
| `BOOTSTRAP_SUPER_ADMIN_EMAIL` | No   | Email that gets super-admin role on first login |
| `MAX_JD_CHARS`             | No       | Max job description length (default 20 000)    |

\* At least one LLM provider key is required.

Full variable reference: `backend/.env.example`
