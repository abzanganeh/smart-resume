# Staging deployment runbook

Last updated: 2026-08-17 (post PR #66).

This is the operator checklist for the **first staging deploy** of Smart Resume.
Code readiness is tracked in `docs/IMPLEMENTATION_PLAN.md` §11 (Release Phase 2).
Local design docs under `docs/` are gitignored; this file is the tracked operator guide.

---

## 1. Identity and auth (already implemented)

Smart Resume does **not** use an external IdP product (no Supabase Auth for the main app).

| Layer | Technology | Canonical user id |
|-------|------------|-------------------|
| Browser session | NextAuth.js v5 (encrypted cookie) | — |
| API identity | FastAPI + Postgres `users` table | `users.id` (UUID) |
| API tokens | HS256 access JWT (15 min) + refresh cookie (rotation) | tied to `users.id` |

**Sign-in methods:** email/password, Google SSO, GitHub SSO.

**OAuth flow:** NextAuth completes the provider exchange → frontend calls
`POST /api/auth/callback` with `id_token` or `access_token` → backend upserts
`(auth_provider, provider_id)` and returns tokens embedded in the NextAuth session
as `backendAccessToken`.

**Staging requirements (`APP_ENV=staging`):**

- `AUTH_DISABLE` is **ignored** (auth always enforced)
- Set `AUTH_SECRET`, `BYOK_ENCRYPTION_KEY`, `NEXTAUTH_SECRET`
- Register OAuth redirect URIs (Google Console + GitHub app):
  - `{FRONTEND_BASE_URL}/api/auth/callback/google`
  - `{FRONTEND_BASE_URL}/api/auth/callback/github`
  - `{FRONTEND_BASE_URL}/auth/extension/google/callback` (extension; optional until published)
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

```bash
# 1. Clone and configure
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local
cp .env.example .env                    # root OAuth vars for compose

# 2. Set APP_ENV=staging in backend/.env
# 3. Fill required secrets (see §3)

# 4. Migrate
docker compose up -d postgres redis
cd backend && uv run alembic upgrade head

# 5. Start app
docker compose up -d --build

# 6. Verify
curl -sf http://localhost:8000/health   # or /docs
curl -sf http://localhost:3000
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
| `GITHUB_CLIENT_ID/SECRET` | frontend | GitHub SSO (optional but planned) |
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

Run on staging after deploy. Automated CI already covers unit/integration/e2e smoke on every PR.

### Auth

- [ ] Register with email/password → lands on onboarding
- [ ] Complete onboarding → dashboard
- [ ] Google SSO login → `backendAccessToken` present; `/api/auth/me` succeeds
- [ ] Logout + refresh rotation (no reuse after logout-all)

### Wizard / tailoring

- [ ] Upload resume ≥ 200 chars → parse succeeds
- [ ] Empty/short resume → clear 422 error (not generic 500)
- [ ] Paste JD → Phase 1 keywords run
- [ ] Your Info pre-fill from parsed resume (refresh on info step)
- [ ] Phase 3 rewrite completes; guard banner if metrics/titles auto-corrected
- [ ] Version restore creates a **new** snapshot number
- [ ] Export PDF/DOCX

### Billing (Stripe test mode)

- [ ] `/billing/prices` returns tiers
- [ ] Checkout → webhook → subscription active
- [ ] Insufficient credits → 402 with actionable message

### Regression spot-checks (from recent PRs)

- [ ] Two-tone JD comparison: output register differs between JDs
- [ ] One Inc regression: no fabricated metrics; education/projects present
- [ ] Checkup → “Tailor this resume” handoff pre-fills resume text

### Optional integrations

- [ ] Flint “Open in Flint” handoff (`Flint/docs/STRATEGY_B_E2E_RUNBOOK.md`)
- [ ] Chrome extension JD capture (requires `EXTENSION_AUTH_ENABLED=true`)

---

## 6. Rollback

- **App regression:** redeploy previous image/tag; no schema downgrade unless migration doc says safe
- **Bad migration:** forward-fix migration preferred over destructive rollback
- **Stripe misconfiguration:** disable checkout via feature flag; fix `PlanConfig` / webhook secret; replay events from Stripe dashboard

---

## 7. What remains post-staging (code backlog)

Not blocking first staging deploy:

- UX flow consolidation (merge wizard steps T1+T2)
- RP4 Steps 27–38 (dashboard hardening, notifications, admin UI polish, compliance pages)
- Full app Terraform / managed CI deploy pipeline

See `docs/IMPLEMENTATION_PLAN.md` for the full RP2–RP4 step list.
