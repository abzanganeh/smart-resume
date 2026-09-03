# Staging & production deployment runbook

Last updated: 2026-08-20 (Flint Apply rebrand — docs/env; UI rename in progress).

This is the operator checklist for deploying **Flint Apply** ([flintapply.com](https://flintapply.com)),
a product of **The Flint AI** ([theflintai.com](https://theflintai.com)).
Code readiness is tracked in `docs/IMPLEMENTATION_PLAN.md` §11 (Release Phase 2).
Local design docs under `docs/` are gitignored; this file is the tracked operator guide.

---

## 1. Identity and auth (already implemented)

Flint Apply does **not** use an external IdP product (no Supabase Auth for the main app).

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

**Local staging simulation** (host **3001/8001** — Kia/Trust may keep **3000**; FlintApply must never bind host 3000):

```bash
# 1. Generate staging env (gitignored *.env files)
python3 scripts/setup-staging-env.py --local-sim   # dummy Stripe IDs for local boot only
# Or omit --local-sim and fill real Stripe test keys in backend/.env.staging

# 2. Validate before boot (backend aborts on startup_price_gap in staging)
python3 scripts/setup-staging-env.py --check

# 3. Start stack (postgres/redis + backend + frontend)
docker compose -f docker-compose.yml -f docker-compose.staging.yml -f docker-compose.local-sim.yml up -d --build

# 4. Automated smoke (HTTP)
chmod +x scripts/staging-smoke.sh
./scripts/staging-smoke.sh

# 5. Manual UI checklist — STAGING.md §5
```

Or use the helper (same local-sim path, pins ports 3001/8001):

```bash
chmod +x scripts/desktop-staging-local-sim-up.sh
./scripts/desktop-staging-local-sim-up.sh
```

**Production-like local staging** (same workstation, no `local-sim.yml`):

Use this when you need real Stripe **test** keys, Resend delivery, and signup cap
`SIGNUP_IP_DAILY_LIMIT=15` — still on host **3001/8001**, not a second cloud deploy.

1. Run `python3 scripts/setup-staging-env.py` **without** `--local-sim` and fill
   real `sk_test_*` keys + Stripe price IDs in `backend/.env.staging`.
2. Boot with **two** compose files only (no `docker-compose.local-sim.yml`):

```bash
STAGING_FRONTEND_PORT=3001 STAGING_BACKEND_PORT=8001 \
  docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d --build
```

3. Forward Stripe webhooks: `stripe listen --forward-to localhost:8001/api/billing/webhook`
4. Run smoke with explicit URLs: `API_URL=http://localhost:8001 FRONTEND_URL=http://localhost:3001 ./scripts/staging-smoke.sh`

Keep `REQUIRE_MAILPIT=1` for localhost smoke (default). Do **not** set
`REQUIRE_MAILPIT=0` on the workstation — that skips verify-before-spend and is
only for HTTPS production smoke (`production-smoke.sh`). For automated verify
unlock, use **local-sim** (Mailpit) above instead of this path.

Verify email goes through Resend (not Mailpit). Mailpit may still start from the
base compose file and bind on all interfaces without the `local-sim` overlay —
keep the workstation firewall enabled. Do **not** run `PRODUCTION_ENV_CHECK=1
./scripts/production-preflight.sh` or `./scripts/production-smoke.sh` on localhost;
those gates target HTTPS VM deploy (§8).

**VM / public staging** (ports `3000`/`8000` behind TLS):

```bash
cp .env.staging.example .env.staging
cp backend/.env.staging.example backend/.env.staging
# Set STAGING_FRONTEND_PORT=3000 STAGING_BACKEND_PORT=8000 in .env.staging
# Set FRONTEND_BASE_URL / NEXTAUTH_URL to https://your-staging-domain
# See infra/caddy/Caddyfile.staging.example (staging) or Caddyfile.production.example (flintapply.com)

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

### Dashboard guided journey (B1–B8)

- [ ] Dashboard step stack shows 7 steps: Master resume → Job roles → Search → Capture JD → Tailor → Apply (autofill) → Track applications; Flint desktop in a separate "Coming soon" block (not numbered)
- [ ] Landing journey shows 7 scroll stages (A–G) aligned with dashboard; Flint desktop in separate "Coming soon" block below the rail
- [ ] Job roles: pick ≥1 title (up to 12); add custom titles; regenerate after master resume change is free
- [ ] Nav pillar labels: **Dashboard**, **Applications** (not Tracker); mobile nav has no duplicate Dashboard link
- [ ] Delete tailored resume confirms no credit refund
- [ ] `./scripts/staging-smoke.sh` passes against staging API/frontend URLs

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
- [ ] `/jobs` **Match my resume** tab (subscribed + master resume on profile) → ranked results with match score badge
- [ ] Match without master resume → error with link to profile
- [ ] **Track application** on job card → `/tracker/{id}` draft
- [ ] **Tailor Resume** → session with JD prefilled
- [ ] `/tracker` kanban drag updates status; detail page loads
- [ ] Funnel summary strip at the top of `/tracker` reflects `GET /api/applications/funnel`
- [ ] Create until active limit (free = 10) → 409 banner "You have reached your plan's active tracker limit"
- [ ] Try re-creating "Software Engineer" at "Google, Inc." within 30 days of an existing row → duplicate modal, "Add anyway" succeeds; double-click the button and confirm only one row is created (button shows "Adding…" while pending)
- [ ] Archive a row → active count drops, `?archived=true` filter shows it, drag disabled
- [ ] Unarchive at the active limit → 409 `tracker_limit_reached`
- [ ] Dashboard "Applications" step reads total from `funnel.total` (not full-row list)

### Billing (Stripe test mode)

- [ ] `/billing/prices` returns tiers
- [ ] Checkout → webhook → subscription active
- [ ] Insufficient credits → 402 with actionable message

### Regression spot-checks (from recent PRs)

- [ ] Two-tone JD comparison: output register differs between JDs
- [ ] One Inc regression: no fabricated metrics; education/projects present
- [ ] Checkup → “Tailor this resume” handoff pre-fills resume text
- [ ] Free-tier registration grant is **3 credits**: `POST /api/auth/register` response contains `credit_balance: 3`. If staging still returns 6, PATCH `/api/admin/credits/free-grant` — existing `tier_limits_config` rows are not overwritten by a code-seed change.
- [ ] Premium plans expose `tracker_active_limit: 250` on `/api/subscriptions/current` (soft cap; marketing still says "unlimited")

### Extension & autofill (manual)

Requires `EXTENSION_AUTH_ENABLED=true` and a browser with the Flint Apply browser extension loaded.

- [ ] Extension OAuth callback registered; sign-in from extension yields valid backend token
- [ ] Capture JD on Greenhouse → tailor in web app → return to apply form
- [ ] Autofill overlay lists recent tailored session for current host (`GET /api/job-descriptions/recent-tailored`)
- [ ] Autofill payload for Greenhouse includes `job_application[email]` selectors; LinkedIn/Lever/Ashby return heuristic keys with empty selectors
- [ ] 409 before tailor shows “Resume not tailored yet” in extension (`resume_not_tailored_yet`)
- [ ] Autofill payload never includes resume summary text in contact fields
- [ ] Flint “Open in Flint” handoff (`Flint/docs/STRATEGY_B_E2E_RUNBOOK.md`)

---

## 6. Rollback

- **App regression:** redeploy previous image/tag; no schema downgrade unless migration doc says safe
- **Bad migration:** forward-fix migration preferred over destructive rollback
- **Stripe misconfiguration:** disable checkout via feature flag; fix `PlanConfig` / webhook secret; replay events from Stripe dashboard
- **⚠ Alembic 0031 (`archived_at`)** is **data-destructive on downgrade**: dropping the column loses archive timestamps and the tracker will re-count archived rows against the active limit. Before any downgrade in a live env, dump `(id, archived_at)` for non-null rows first.

---

## 7. What remains post-staging (code backlog)

Not blocking first staging deploy:

- RP4 Steps 27–38 — **mostly implemented** (dashboard, tracker, notifications, export/closure, admin/compliance). Remaining work is **manual STAGING.md §5** and production Terraform apply for new EventBridge rules.
- Full app Terraform / managed CI deploy pipeline

See `docs/IMPLEMENTATION_PLAN.md` for the full RP2–RP4 step list.

---

## 8. Production (flintapply.com)

Use the same Docker Compose stack as staging; bind **3000/8000** on the VM and terminate TLS with Caddy.

### DNS

| Host | Purpose |
|------|---------|
| `flintapply.com` | Next.js frontend |
| `api.flintapply.com` | FastAPI backend |

### Environment (production)

**`backend/.env.staging`** (or a dedicated production env file on the server):

```bash
APP_ENV=staging   # or production when APP_ENV=production gates are added
FRONTEND_BASE_URL=https://flintapply.com
ALLOWED_ORIGINS=["https://flintapply.com"]
```

**`.env.staging`** (frontend / compose):

```bash
STAGING_FRONTEND_PORT=3000
STAGING_BACKEND_PORT=8000
NEXTAUTH_URL=https://flintapply.com
NEXT_PUBLIC_SITE_URL=https://flintapply.com
NEXT_PUBLIC_API_URL=https://api.flintapply.com
```

Set OAuth provider redirect URIs to `https://flintapply.com/api/auth/callback/<provider>`.

Stripe webhook endpoint: `https://api.flintapply.com/api/billing/webhook`.

Reverse proxy template: `infra/caddy/Caddyfile.production.example`.

### Deploy

**Do not** use `docker-compose.local-sim.yml` on a public VM (that file blanks Resend and raises signup caps for workstation smoke only).

```bash
# 1. Preflight (on the server, after filling production URLs in env files)
PRODUCTION_ENV_CHECK=1 ./scripts/production-preflight.sh

# 2. Boot stack (ports 3000/8000 behind Caddy — see §2)
docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d --build

# 3. Automated HTTP smoke (registers a user — no Mailpit verify unlock on HTTPS)
CONFIRM_PRODUCTION_SMOKE=1 ./scripts/production-smoke.sh

# 4. Manual UI + billing + admin step pins
#    STAGING.md §5 — confirm gemini-3.5-* pins at /admin/llm
```

Local workstation smoke (ports `3001`/`8001`, Mailpit verify flow):

```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml -f docker-compose.local-sim.yml up -d --build
./scripts/staging-smoke.sh
```

---

## 9. Company & legal entity migration (The Flint AI)

**Product:** Flint Apply · **Company:** The Flint AI *(legal entity name TBD — see Thread 1 charter)* · **Domains:** [flintapply.com](https://flintapply.com), [theflintai.com](https://theflintai.com)

This section is the operator checklist for moving from the current **personal**
licensor/controller (`Alireza Barzin Zanganeh`, `privacy@zanganeai.com`) to
**The Flint AI** as the published company. It is intentionally separate from
code deploy: UI can rebrand before the entity exists; legal pages must not claim
a company that is not yet registered.

Cross-reference: `docs/IMPLEMENTATION_PLAN.md` §11g (engineering slices) and
M16 task file `.cursor/skills/resume-loop-engineering/tasks/marketing-motion-and-intro.md`.

### Phase A — UI & marketing rebrand (no entity required)

Can ship on staging while entity work is in progress.

- [x] Centralise names in `frontend/lib/brand.ts` (`FlintApply`, `by The Flint AI`, copyright line)
- [x] Replace user-facing **TalioCV** strings in frontend + backend copy (non-legal surfaces; `/legal/*` deferred to Phase C)
- [ ] Footer marketing line: `© {year} The Flint AI` (not personal name)
- [ ] Intro overlay greeting uses **FlintApply** (see `lib/marketing/intro.ts`)
- [ ] Replace brand assets under `frontend/public/brand/` and app icons (`favicon.ico`, `icon.png`, `opengraph-image.png`)
- [ ] Re-capture `ProductScreenshot` after UI shows FlintApply (generated screenshots are not acceptable)
- [ ] `NEXT_PUBLIC_SITE_URL` / OAuth app display names updated to Flint Apply where provider consoles allow
- [ ] **Do not** change BSL licensor, privacy controller, or DPO contact yet — see Phase C

### Phase B — Register The Flint AI (operator / legal, not code)

Blockers for Phase C. Record completion dates here when done.

- [ ] Choose jurisdiction and entity type (LLC, corp, etc.) — **legal counsel**
- [ ] Register **The Flint AI** (or exact legal name, e.g. *The Flint AI, LLC*)
- [ ] Obtain EIN / tax ID
- [ ] Open business bank account
- [ ] Register domains if not already owned: `flintapply.com`, `theflintai.com`
- [ ] Create company email mailboxes (minimum):
  - `privacy@theflintai.com` (DPO / privacy contact)
  - `licensing@theflintai.com` (BSL commercial requests)
  - `security@theflintai.com` (SECURITY.md contact, if split from privacy)
  - `hello@` or `support@` for general product contact (optional but recommended)
- [ ] Stripe account: business profile → **The Flint AI**, linked bank, live keys for production
- [ ] Google Cloud / GitHub OAuth apps: publisher name → The Flint AI; redirect URIs → `flintapply.com`

### Phase C — Legal & compliance document migration (after Phase B)

Only merge when the entity in Phase B matches what the documents claim.

| File / surface | Current | Target |
|---|---|---|
| `LICENSE` BSL Licensor | Alireza Barzin Zanganeh | The Flint AI (exact legal name) |
| `COMMERCIAL.md` contact | `licensing@zanganehai.com` | `licensing@theflintai.com` |
| `SECURITY.md` | personal / zanganeh domain | The Flint AI + company security contact |
| `app/legal/privacy/page.tsx` | personal data controller | The Flint AI as controller |
| `app/legal/terms/page.tsx` | personal licensor references | The Flint AI |
| `app/legal/contact/page.tsx` | DPO personal routing | The Flint AI DPO |
| `app/legal/ccpa/page.tsx` | personal business name | The Flint AI |
| `app/legal/sub-processors/page.tsx` | verify controller name | The Flint AI |
| `backend/app/config.py` / email templates | `FRONTEND_BASE_URL`, from-address | company domain |
| `frontend/tests/e2e/legal.spec.ts` | asserts personal copyright + DPO email | update to company assertions |
| `backend/tests/unit/test_contact_authority.py` | DPO routing tests | update fixtures |

Checklist:

- [ ] Counsel reviews privacy policy + terms for controller/licensor change
- [ ] All five `/legal/*` pages updated and cross-linked
- [ ] Footer DPO link → `privacy@theflintai.com` (or dedicated DPO address)
- [ ] Transactional email `From:` uses company domain (SPF/DKIM on theflintai.com)
- [ ] Sub-processor list still accurate after any vendor re-contracting
- [ ] Re-run `legal.spec.ts` and backend legal integration tests

### Phase D — Production cutover (after Phase C + §8 deploy)

- [ ] Production env vars (§8) use `https://flintapply.com` and company emails
- [ ] OAuth consent screens show **Flint Apply** by **The Flint AI**
- [ ] Stripe Checkout / Customer Portal show registered business name
- [ ] Manual smoke §5 on production with legal footer assertions
- [ ] Optional: cookie/consent banner vendor updated if controller ID changed

### Phase E — Deferred (post-launch)

- [ ] Customer logo / testimonial section on landing (only when real customers exist)
- [ ] Press / “As seen on” row (only with verifiable citations)
- [ ] Per-capability marketing subpages (`/product/story-mode`, etc.)
- [ ] `/learn` content hub (writing project)

### Naming note — two different “Flint” products

The codebase already integrates with the **Flint desktop interview app**
(`OpenInFlintButton`, `createFlintHandoff`). After rebrand, user-facing copy must
keep that distinction clear, e.g. **“Open in Flint Live”** or **“Open in Flint
(desktop)”** so it is not confused with **Flint Apply** (this web product).

