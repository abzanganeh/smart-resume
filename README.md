# Smart Resume Agent

An AI-powered web application that tailors your resume to any job description using ATS keyword analysis and evidence-based resume quality rules.

> **No API key setup required.** Users enter their own key directly in the browser — it never leaves their device.

---

## Quick Start

### Run with Docker Compose (recommended)

```bash
docker compose up
```

Opens:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

No `.env` configuration needed for local use — just open the app, pick your AI provider, and paste your key in the UI.

### Run locally (development)

**Backend:**
```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
cp .env.local.example .env.local
pnpm install
pnpm dev
```

---

## How API Keys Work (BYOK)

The app uses a **Bring Your Own Key** model:

1. In the Job Description step, open the **AI Provider & Key** card
2. Pick a provider (OpenAI, Anthropic, Gemini, OpenRouter, or Ollama)
3. Paste your API key (link to each provider's key dashboard is shown)
4. Click **Use this provider**

Your key is stored in your browser's `sessionStorage` only — it disappears when you close the tab and is **never logged, stored, or sent anywhere except directly to the LLM API**.

### Supported providers

| Provider | Key dashboard | Recommended model |
|---|---|---|
| OpenAI | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | `gpt-4o` |
| Anthropic | [console.anthropic.com](https://console.anthropic.com/) | `claude-opus-4-5` |
| Google Gemini | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | `gemini-1.5-pro` |
| OpenRouter | [openrouter.ai/keys](https://openrouter.ai/keys) | any available model |
| Ollama (local, free) | — install from [ollama.ai](https://ollama.ai) | `llama3.1:8b` |

### Self-hosting with a pre-configured key (optional)

If you're deploying this for a team and want to pre-configure a key so users don't need their own, add it to `backend/.env`:

```bash
cd backend
cp .env.example .env
# Fill in the key for one provider, e.g.:
# OPENAI_API_KEY=sk-...
# LLM_PROVIDER=openai
# LLM_MODEL=gpt-4o
```

The UI will show a green "configured" badge on that provider. Users can still override it with their own key.

### Adding a new LLM provider (3 steps)

1. Create `backend/backend/llm/providers/my_provider_adapter.py` — implement `LLMClient`
2. Add a `case "my_provider":` block in `backend/backend/llm/factory.py`
3. Add the provider entry to `backend/backend/llm/model_catalog.py`

---

## How It Works

The agent runs 4 sequential phases:

| Phase | What it does |
|---|---|
| 1 — Keywords | Extracts must-have and nice-to-have ATS keywords from the JD |
| 2 — Audit | Gaps every missing keyword, weak bullet, and cliché in your resume |
| 3 — Rewrite | Rewrites with exact JD phrasing; never fabricates metrics |
| 4 — QA | Runs the 8-point quality checklist before export |

Each phase streams results to the browser via SSE as the AI works.

---

## Session Notes

- Sessions are anonymous — no account required
- Sessions expire after **24 hours**; a warning banner appears at the 20-hour mark
- Resume content is never logged or stored beyond the session TTL

---

## Architecture

See `docs/SYSTEM_DESIGN.md` for the full architecture, API contracts, data models, and design decisions.
