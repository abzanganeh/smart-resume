# TalioCV — Backend

FastAPI API for the TalioCV.

## Run locally

From this directory (`smart-resume/backend/`):

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

- Health: http://localhost:8000/health
- API docs: http://localhost:8000/docs

## Config (optional)

Copy `.env.example` to `.env` only if you want server-side defaults (e.g. team deployment):

```bash
cp .env.example .env
```

For local dev without Redis:

```env
USE_IN_MEMORY_STORE=true
```

Regular users bring their own API key in the browser — no keys required in `.env`.

## Package layout

```
backend/
├── app/          ← Python package (import as `app.*`)
├── pyproject.toml
├── Dockerfile
└── .env          ← local only, gitignored
```
