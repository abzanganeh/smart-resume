#!/usr/bin/env python3
"""Restore common local dev env values from repo artifacts.

Safe to re-run. Never prints secret values.

Usage (repo root):
  python3 scripts/setup-dev-env.py
"""

from __future__ import annotations

import json
import re
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOOGLE_JSON = ROOT / "docs" / (
    "client_secret_399906112759-f7o3grjq45j9nv77p0hpedc480ab73mi"
    ".apps.googleusercontent.com.json"
)


def load_google_oauth() -> tuple[str, str] | None:
    if not GOOGLE_JSON.is_file():
        return None
    data = json.loads(GOOGLE_JSON.read_text())
    web = data.get("web") or {}
    client_id = (web.get("client_id") or "").strip()
    client_secret = (web.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        return None
    return client_id, client_secret


def set_env_var(path: Path, key: str, value: str) -> bool:
    """Set or append KEY=value. Returns True if file changed."""
    text = path.read_text() if path.is_file() else ""
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    line = f"{key}={value}"
    if pattern.search(text):
        new_text = pattern.sub(line, text)
    else:
        new_text = text.rstrip() + ("\n" if text else "") + line + "\n"
    if new_text == text:
        return False
    path.write_text(new_text)
    return True


def ensure_secret(path: Path, key: str, length_hex: int = 32) -> bool:
    text = path.read_text() if path.is_file() else ""
    match = re.search(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    current = (match.group(1).strip() if match else "")
    if current and current not in {"local-docker-dev-secret-change-me", ""}:
        return False
    return set_env_var(path, key, secrets.token_hex(length_hex))


def main() -> None:
    root_env = ROOT / ".env"
    backend_env = ROOT / "backend" / ".env"

    if not root_env.is_file():
        root_env.write_text((ROOT / ".env.example").read_text())
        print(f"Created {root_env.relative_to(ROOT)} from .env.example")

    if not backend_env.is_file():
        backend_env.write_text((ROOT / "backend" / ".env.example").read_text())
        print(f"Created {backend_env.relative_to(ROOT)} from backend/.env.example")

    changed: list[str] = []

    google = load_google_oauth()
    if google:
        client_id, client_secret = google
        for path, keys in (
            (root_env, ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET")),
            (backend_env, ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET")),
        ):
            if set_env_var(path, keys[0], client_id):
                changed.append(f"{path.name}:{keys[0]}")
            if set_env_var(path, keys[1], client_secret):
                changed.append(f"{path.name}:{keys[1]}")
    else:
        print("Google OAuth JSON not found in docs/ — skip SSO restore.")

    # Host ports for docker-compose (postgres 54325, redis 6380).
    docker_db = "postgresql+asyncpg://smart_resume:password@localhost:54325/smart_resume"
    docker_redis = "redis://localhost:6380"

    if set_env_var(backend_env, "DATABASE_URL", docker_db):
        changed.append("backend/.env:DATABASE_URL")
    if set_env_var(backend_env, "REDIS_URL", docker_redis):
        changed.append("backend/.env:REDIS_URL")
    if set_env_var(backend_env, "APP_ENV", "local"):
        changed.append("backend/.env:APP_ENV")
    if set_env_var(backend_env, "ACCESS_TOKEN_TTL_SECONDS", "86400"):
        changed.append("backend/.env:ACCESS_TOKEN_TTL_SECONDS")
    if set_env_var(backend_env, "FRONTEND_BASE_URL", "http://localhost:3000"):
        changed.append("backend/.env:FRONTEND_BASE_URL")

    if ensure_secret(root_env, "NEXTAUTH_SECRET"):
        changed.append(".env:NEXTAUTH_SECRET")
    if ensure_secret(backend_env, "AUTH_SECRET"):
        changed.append("backend/.env:AUTH_SECRET")
    if ensure_secret(backend_env, "BYOK_ENCRYPTION_KEY"):
        changed.append("backend/.env:BYOK_ENCRYPTION_KEY")

    print("\nUpdated:" if changed else "\nNo changes needed.")
    for item in changed:
        print(f"  - {item}")

    print("\n--- Manual checklist (fill in backend/.env) ---")
    print("  LLM (pick one provider):")
    print("    gemini  → GOOGLE_API_KEY + LLM_PROVIDER=gemini + LLM_MODEL=gemini-2.5-flash")
    print("    openai  → OPENAI_API_KEY + LLM_PROVIDER=openai + LLM_MODEL=gpt-4o")
    print("    ollama  → LLM_PROVIDER=ollama + LLM_MODEL=llama3.1:8b (no key; run ollama locally)")
    print("\n--- Then start ---")
    print("  docker compose up --build")
    print("\n--- Google sign-in ---")
    print("  Web redirect URI:       http://localhost:3000/api/auth/callback/google")
    print("  Extension redirect URI: http://localhost:3000/auth/extension/google/callback")
    print("  Add BOTH in Google Cloud Console → OAuth client → Authorized redirect URIs")
    print("  After rebuild, verify: curl -s http://localhost:3000/api/auth/providers | grep google")


if __name__ == "__main__":
    main()
