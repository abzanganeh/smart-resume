# Staging deployment runbook

Last updated: 2026-08-18 (post PR #71 — staging deploy tooling).

This is the operator checklist for the **first staging deploy** of TalioCV.
Code readiness is tracked in `docs/IMPLEMENTATION_PLAN.md` §11 (Release Phase 2).
Local design docs under `docs/` are gitignored; this file is the tracked operator guide.

---

## 1. Identity and auth (already implemented)

TalioCV does **not** use an external IdP product (no Supabase Auth for the main app).

| Layer | Technology | Canonical user id |
|-------|------------|-------------------|
| Browser session | NextAuth.js v5 (encrypted cookie) | — |
| API identity | FastAPI + Postgres `users` table | `users.id` (UUID) |
| API tokens | HS256 access JWT (15 min) + refresh cookie (rotation) | tied to `users.id` |

**Sign-in methods:** email/password, Google SSO, GitHub SSO, LinkedIn SSO (Microsoft Entra optional).

**OAuth flow:** NextAuth completes the provider exchange → frontend calls
`POST /api/auth/callback` with `id_token` or `access_token` → backend upserts
`(auth_provider, provider_id)` and returns tokens embedded in the NextAuth session
as `backendAccessToken`.

**Staging requirements (`APP_ENV=staging`):**

- `AUTH_DISABLE` is **ignored** (auth always enforced)
- Set `AUTH_SECRET`, `BYOK_ENCRYPTION_KEY`, `NEXTAUTH_SECRET`
- Register OAuth redirect URIs per provider:
  - Google: `{FRONTEND_BASE_URL}/api/auth/callback/google`
  - GitHub: `{FRONTEND_BASE_URL}/api/auth/callback/github`
  - LinkedIn: `{FRONTEND_BASE_URL}/api/auth/callback/linkedin`
  - Microsoft: `{FRONTEND_BASE_URL}/api/auth/callback/microsoft-entra-id`
  - Extension (optional): `{FRONTEND_BASE_URL}/auth/extension/google/callback`
- Set `FRONTEND_BASE_URL` and `NEXTAUTH_URL` to the public staging frontend URL
- Configure CORS: add staging origin to `ALLOWED_ORIGINS` in backend env

**Bootstrap admin (one-time):**

```bash
BOOTSTRAP_SUPER_ADMIN_EMAIL=you@example.com
BOOTSTRAP_SUPER_ADMIN_PASSWORD=<strong-password>   # required in staging
```

Restart backend once; enroll TOTP on first `/admin/auth` login.

---

## 2. Infrastructure (fastest path: Docker Compose on a VM)

There is **no Terraform for the Next.js/FastAPI app** today. Terraform under
`infra/terraform/` covers **job-search Lambdas only** (Apify cache, alerts).

### Minimum staging stack

| Service | Notes |
|---------|--------|
| Postgres 16 + pgvector | `docker compose` service or RDS |
| Redis 7 | refresh-token store, rate limits |
| Backend | `backend/Dockerfile`, port 8000 |
| Frontend | `frontend/Dockerfile`, port 3000 |
| TLS reverse proxy | nginx/Caddy in front of 3000 + 8000 |

### Deploy sequence

**Local staging simulation** (ports `3001`/`8001` so `pnpm dev` can keep `:3000`):

```bash
# 1. Generate staging env (gitignored *.env files)
python3 scripts/setup-staging-env.py --local-sim   # dummy Stripe IDs for local boot only
# Or omit --local-sim and fill real Stripe test keys in backend/.env.staging

# 2. Validate before boot (backend aborts on startup_price_gap in staging)
python3 scripts/setup-staging-env.py --check

# 3. Start stack (postgres/redis + backend + frontend)
docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d --build

# 4. Automated smoke (HTTP)
chmod +x scripts/staging-smoke.sh
./scripts/staging-smoke.sh

# 5. Manual UI checklist — STAGING.md §5
```

**VM / public staging** (ports `3000`/`8000` behind TLS):

```bash
cp .env.staging.example .env.staging
cp backend/.env.staging.example backend/.env.staging
# Set STAGING_FRONTEND_PORT=3000 STAGING_BACKEND_PORT=8000 in .env.staging
# Set FRONTEND_BASE_URL / NEXTAUTH_URL to https://your-staging-domain
# See infra/caddy/Caddyfile.staging.example

docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d --build
./scripts/staging-smoke.sh   # with API_URL / FRONTEND_URL env overrides
```

Legacy single-file dev path (not recommended for staging gates):

```bash
cp backend/.env.example backend/.env
cp .env.example .env
# Set APP_ENV=staging manually; fill §3 secrets
docker compose up -d postgres redis
cd backend && uv run alembic upgrade head
docker compose up -d --build
curl -sf http://localhost:8000/health
```

### Optional: job-search infra (Phase 3)

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # environment = "staging"
terraform init && terraform apply
```

Requires `APIFY_API_TOKEN`, `POSTGRES_URL`, and Lambda zip artifacts (`infra/terraform/build.sh`).

---

## 3. Required environment variables (staging)

Copy from `backend/.env.example` and `frontend/.env.local.example`.

### Must-have before go-live

| Variable | Where | Purpose |
|----------|-------|---------|
| `APP_ENV=staging` | backend | production-grade security gates |
| `DATABASE_URL` | backend | Postgres + asyncpg |
| `REDIS_URL` | backend | sessions / refresh tokens |
| `AUTH_SECRET` | backend | JWT signing (32-byte hex) |
| `BYOK_ENCRYPTION_KEY` | backend | TOTP/BYOK encryption |
| `NEXTAUTH_SECRET` | frontend | NextAuth cookie encryption |
| `NEXTAUTH_URL` | frontend | public frontend URL |
| `FRONTEND_BASE_URL` | backend | CORS, email links, extension callback |
| `ALLOWED_ORIGINS` | backend | JSON array with staging frontend origin |
| `GOOGLE_CLIENT_ID/SECRET` | both | Google SSO |
| `GITHUB_CLIENT_ID/SECRET` | both | GitHub SSO |
| `LINKEDIN_CLIENT_ID/SECRET` | both | LinkedIn SSO |
| `GEMINI_API_KEY` | backend | platform LLM (default provider) |
| `OPENAI_EMBEDDING_KEY` | backend | master-resume embeddings (or reuse OpenAI key) |
| `STRIPE_SECRET_KEY` | backend | billing |
| `STRIPE_WEBHOOK_SECRET` | backend | webhook signature verification |
| `RESEND_API_KEY` | backend | verification / password-reset email |

### Stripe price IDs

Either seed `PlanConfig` rows in Postgres **or** set bootstrap env vars
(`STRIPE_PRICE_WEEKLY`, `STRIPE_PRICE_MONTHLY_PRO`, etc.) per `backend/.env.example`.

On boot, missing price mappings emit `startup_price_gap` warnings; staging gate
should treat unresolved canonical codes as a blocker.

### Stripe webhook

1. Create endpoint: `https://<staging-api>/api/billing/webhook`
2. Subscribe to: `checkout.session.completed`, `customer.subscription.*`, `invoice.*`
3. Paste signing secret into `STRIPE_WEBHOOK_SECRET`
4. Replay-test with Stripe CLI before opening staging to testers:

```bash
stripe listen --forward-to localhost:8000/api/billing/webhook
stripe trigger customer.subscription.updated
```

---

## 4. Pre-deploy data migration

If migrating existing subscribers from legacy plan codes:

```bash
cd backend
uv run python scripts/migrate_subscribers.py              # dry-run first
uv run python scripts/migrate_subscribers.py --apply      # DB only
uv run python scripts/migrate_subscribers.py --apply --sync-stripe   # + Stripe
```

Review dry-run counts before `--apply`.

---

## 5. Manual smoke checklist (Release Phase 2)

Run on staging after deploy. Automated CI covers unit/integration tests and e2e smoke (`legal`, `auth`, `jobs`, `tracker`) on every PR.

### Auth

- [ ] Register with email/password → lands on onboarding
- [ ] Complete onboarding → dashboard
- [ ] Google SSO login → `backendAccessToken` present; `/api/auth/me` succeeds
- [ ] Logout + refresh rotation (no reuse after logout-all)

### Wizard / tailoring

- [ ] Upload resume ≥ 200 chars → parse succeeds
- [ ] Empty/short resume → clear 422 error (not generic 500)
- [ ] Paste JD → **Analysis** tab: single **Run analysis** chains Phase 1 keywords then Phase 2 audit
- [ ] Legacy `?step=keywords` / `?step=audit` redirect to `?step=analysis`
- [ ] Your Info pre-fill from parsed resume (refresh on info step)
- [ ] Phase 3 rewrite completes; guard banner if metrics/titles auto-corrected
- [ ] **Track this application** on rewrite tab creates draft in tracker
- [ ] Version restore creates a **new** snapshot number
- [ ] Export PDF/DOCX

### Job search & tracker

- [ ] `/jobs` search (subscribed user) → results, stale banner when provider degraded
- [ ] **Track application** on job card → `/tracker/{id}` draft
- [ ] **Tailor Resume** → session with JD prefilled
- [ ] `/tracker` kanban drag updates status; detail page loads

### Billing (Stripe test mode)

- [ ] `/billing/prices` returns tiers
- [ ] Checkout → webhook → subscription active
- [ ] Insufficient credits → 402 with actionable message

### Regression spot-checks (from recent PRs)

- [ ] Two-tone JD comparison: output register differs between JDs
- [ ] One Inc regression: no fabricated metrics; education/projects present
- [ ] Checkup → “Tailor this resume” handoff pre-fills resume text

### Extension & autofill (manual)

- [ ] `EXTENSION_AUTH_ENABLED=true`; OAuth callback registered for extension
- [ ] Capture JD on Greenhouse → tailor in web app → return to apply form
- [ ] Autofill overlay lists recent tailored session for current host
- [ ] 409 before tailor shows “Resume not tailored yet” in extension
- [ ] Flint “Open in Flint” handoff (`Flint/docs/STRATEGY_B_E2E_RUNBOOK.md`)

---

## 6. Rollback

- **App regression:** redeploy previous image/tag; no schema downgrade unless migration doc says safe
- **Bad migration:** forward-fix migration preferred over destructive rollback
- **Stripe misconfiguration:** disable checkout via feature flag; fix `PlanConfig` / webhook secret; replay events from Stripe dashboard

---

## 7. What remains post-staging (code backlog)

Not blocking first staging deploy:

- RP4 Steps 27–38 (dashboard hardening, notifications platform, admin UI polish, compliance pages)
- Full app Terraform / managed CI deploy pipeline
- Job search “Match my resume” UI (`/api/jobs/match` backend exists)

See `docs/IMPLEMENTATION_PLAN.md` for the full RP2–RP4 step list.
