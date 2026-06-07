#!/bin/sh
set -e
cd /app
echo "[entrypoint] Running database migrations..."
uv run alembic upgrade head
echo "[entrypoint] Starting API server..."
exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
