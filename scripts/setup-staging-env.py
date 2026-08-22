#!/usr/bin/env python3
"""Prepare staging env files for first deploy (local simulation or VM).

Creates gitignored ``.env.staging`` and ``backend/.env.staging`` from tracked
examples, copies OAuth/LLM/Stripe values from existing dev env when present,
and generates required secrets.

Usage (repo root):
  python3 scripts/setup-staging-env.py
  python3 scripts/setup-staging-env.py --check   # validate only, no writes
"""

from __future__ import annotations

import argparse
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_STAGING = ROOT / ".env.staging"
ROOT_EXAMPLE = ROOT / ".env.staging.example"
BACKEND_STAGING = ROOT / "backend" / ".env.staging"
BACKEND_EXAMPLE = ROOT / "backend" / ".env.staging.example"

# Keys copied from dev env when staging value is empty
COPY_FROM_DEV = (
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GITHUB_CLIENT_ID",
    "GITHUB_CLIENT_SECRET",
    "LINKEDIN_CLIENT_ID",
    "LINKEDIN_CLIENT_SECRET",
    "AZURE_AD_CLIENT_ID",
    "AZURE_AD_CLIENT_SECRET",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_EMBEDDING_KEY",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "RESEND_API_KEY",
    "RESEND_FROM_EMAIL",
    "BOOTSTRAP_SUPER_ADMIN_EMAIL",
    "GEMINI_API_KEY",
    "LLM_PROVIDER",
    "LLM_MODEL",
)

STRIPE_PRICE_KEYS = tuple(
    f"STRIPE_PRICE_{suffix}"
    for suffix in (
        "WEEKLY",
        "MONTHLY_PRO",
        "YEARLY_PRO",
        "MONTHLY_PLUS",
        "YEARLY_PLUS",
        "MONTHLY_PREMIUM",
        "YEARLY_PREMIUM",
        "BETTER_PACK",
        "BETTER_MONTHLY",
        "BETTER_YEARLY",
        "BEST_PER_RESUME",
        "BEST_MONTHLY",
        "BEST_YEARLY",
    )
)


def parse_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def render_env(template: Path, values: dict[str, str]) -> str:
    lines: list[str] = []
    for raw in template.read_text().splitlines():
        if raw.strip().startswith("#") or "=" not in raw:
            lines.append(raw)
            continue
        key, _, rest = raw.partition("=")
        key = key.strip()
        if key in values and values[key]:
            lines.append(f"{key}={values[key]}")
        else:
            lines.append(raw)
    return "\n".join(lines) + "\n"


def is_placeholder(value: str) -> bool:
    v = value.strip()
    if not v:
        return True
    if v.endswith("..."):
        return True
    if v in {"sk_test_...", "whsec_...", "price_...", "change-me-in-production"}:
        return True
    return False


def ensure_secret(values: dict[str, str], key: str) -> None:
    if not is_placeholder(values.get(key, "")):
        return
    values[key] = secrets.token_hex(32)


def merge_dev(source: Path, target: dict[str, str], keys: tuple[str, ...]) -> None:
    dev = parse_env(source)
    for key in keys:
        if is_placeholder(target.get(key, "")) and dev.get(key) and not is_placeholder(dev[key]):
            target[key] = dev[key]


def validate(values: dict[str, str]) -> list[str]:
    missing: list[str] = []
    required = (
        "AUTH_SECRET",
        "BYOK_ENCRYPTION_KEY",
        "BOOTSTRAP_SUPER_ADMIN_EMAIL",
        "BOOTSTRAP_SUPER_ADMIN_PASSWORD",
    )
    for key in required:
        if is_placeholder(values.get(key, "")):
            missing.append(key)

    has_llm = not is_placeholder(values.get("GOOGLE_API_KEY", "")) or not is_placeholder(
        values.get("OPENAI_API_KEY", "")
    )
    if not has_llm:
        missing.append("GOOGLE_API_KEY or OPENAI_API_KEY")

    if is_placeholder(values.get("STRIPE_SECRET_KEY", "")):
        missing.append("STRIPE_SECRET_KEY")

    unresolved_prices = [k for k in STRIPE_PRICE_KEYS if is_placeholder(values.get(k, ""))]
    if unresolved_prices:
        missing.append(
            f"Stripe price IDs ({len(unresolved_prices)} unset) — backend aborts on startup_price_gap"
        )

    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Flint Apply staging env files")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate backend/.env.staging only; do not write files",
    )
    parser.add_argument(
        "--local-sim",
        action="store_true",
        help="Fill dummy Stripe price IDs for local docker staging (not for public VM)",
    )
    args = parser.parse_args()

    if args.check:
        if not BACKEND_STAGING.is_file():
            print(f"Missing {BACKEND_STAGING.relative_to(ROOT)} — run without --check first")
            return 1
        gaps = validate(parse_env(BACKEND_STAGING))
        if gaps:
            print("Staging env gaps:")
            for gap in gaps:
                print(f"  - {gap}")
            return 1
        print("Staging env looks ready.")
        return 0

    if not ROOT_EXAMPLE.is_file() or not BACKEND_EXAMPLE.is_file():
        print("Missing .env.staging.example templates")
        return 1

    root_values = parse_env(ROOT_STAGING) if ROOT_STAGING.is_file() else parse_env(ROOT_EXAMPLE)
    backend_values = (
        parse_env(BACKEND_STAGING) if BACKEND_STAGING.is_file() else parse_env(BACKEND_EXAMPLE)
    )

    # Seed from examples when files do not exist yet
    if not ROOT_STAGING.is_file():
        root_values = parse_env(ROOT_EXAMPLE)
    if not BACKEND_STAGING.is_file():
        backend_values = parse_env(BACKEND_EXAMPLE)

    merge_dev(ROOT / ".env", root_values, COPY_FROM_DEV)
    merge_dev(ROOT / "backend" / ".env", backend_values, COPY_FROM_DEV + STRIPE_PRICE_KEYS)

    ensure_secret(backend_values, "AUTH_SECRET")
    ensure_secret(backend_values, "BYOK_ENCRYPTION_KEY")
    ensure_secret(backend_values, "INTERNAL_SCHEDULER_SECRET")
    ensure_secret(root_values, "NEXTAUTH_SECRET")

    if is_placeholder(backend_values.get("BOOTSTRAP_SUPER_ADMIN_PASSWORD", "")):
        backend_values["BOOTSTRAP_SUPER_ADMIN_PASSWORD"] = secrets.token_urlsafe(24)

    if args.local_sim:
        backend_values["STRIPE_SECRET_KEY"] = "sk_test_local_staging_sim"
        backend_values["STRIPE_WEBHOOK_SECRET"] = "whsec_local_staging_sim"
        for key in STRIPE_PRICE_KEYS:
            code = key.removeprefix("STRIPE_PRICE_").lower()
            backend_values[key] = f"price_staging_{code}"

    # Mirror shared secrets
    if backend_values.get("AUTH_SECRET") and is_placeholder(root_values.get("NEXTAUTH_SECRET", "")):
        pass  # already ensured above
    if root_values.get("NEXTAUTH_SECRET"):
        pass

    for oauth_key in COPY_FROM_DEV:
        if oauth_key.startswith(("GOOGLE_", "GITHUB_", "LINKEDIN_", "AZURE_")):
            if root_values.get(oauth_key) and is_placeholder(backend_values.get(oauth_key, "")):
                backend_values[oauth_key] = root_values[oauth_key]
            if backend_values.get(oauth_key) and is_placeholder(root_values.get(oauth_key, "")):
                root_values[oauth_key] = backend_values[oauth_key]

    ROOT_STAGING.write_text(render_env(ROOT_EXAMPLE, root_values))
    BACKEND_STAGING.write_text(render_env(BACKEND_EXAMPLE, backend_values))

    print(f"Wrote {ROOT_STAGING.relative_to(ROOT)}")
    print(f"Wrote {BACKEND_STAGING.relative_to(ROOT)}")

    gaps = validate(backend_values)
    if gaps:
        print("\nFill these before staging boot (backend will refuse startup_price_gap):")
        for gap in gaps:
            print(f"  - {gap}")
        print("\nThen:")
    else:
        print("\nEnv looks complete. Next:")

    print("  docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d --build")
    print("  ./scripts/staging-smoke.sh")
    print("\nBootstrap admin password (one-time, save securely):")
    print(f"  {backend_values.get('BOOTSTRAP_SUPER_ADMIN_PASSWORD', '(generated above)')}")
    return 0 if not gaps else 2


if __name__ == "__main__":
    sys.exit(main())
