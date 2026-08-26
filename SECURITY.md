# Security Policy

## Reporting A Vulnerability

Please report suspected security issues privately.

- Email: `security@zanganehai.com`
- PGP: public key not yet published — request an encryption key at the email
  above for sensitive reports until the fingerprint is posted in this file.
- Preferred format: include steps to reproduce, affected version, impact,
  and any proof-of-concept details.

Do not open public GitHub issues for undisclosed vulnerabilities.

## Response SLA

- Initial acknowledgement: within 24 hours
- Triage decision: within 3 business days
- Status updates: at least every 7 calendar days until resolution
- Target patch timeline:
  - critical/high severity: within 7 days
  - medium severity: within 30 days
  - low severity: next scheduled release

## Scope

This policy covers the Flint Apply repository and official releases at [flintapply.com](https://flintapply.com).

Out of scope:

- social engineering
- denial-of-service without a practical exploit chain
- issues requiring leaked credentials from third parties

## Coordinated Disclosure

We follow coordinated disclosure:

1. You report privately.
2. We confirm and triage.
3. We patch and prepare advisories.
4. We publish a disclosure with credit (if requested).

## Safe Harbor

If you act in good faith, avoid privacy violations and service disruption,
and provide us a reasonable time to remediate before public disclosure, we
will not pursue legal action for your research activity.

## Supply Chain Scanning (OWASP A03 / LLM04)

**Last verified:** 2026-08-21  
**Milestone:** M23 slice A1 (`feature/owasp-2026-baseline`)

Flint Apply ships a Python backend (`uv` + `uv.lock`) and a Next.js frontend
(`pnpm` + `pnpm-lock.yaml`). CI enforces reproducible installs and runs
dependency and secret scans on every push/PR to `main`.

### CI gates

| Gate | Job | Tool | Lockfile enforcement |
|---|---|---|---|
| Python dependency audit | `Security supply chain (A03)` | `uv export` + `pip-audit -r` on `uv.lock` | `uv sync --frozen` |
| Node dependency audit | `Security supply chain (A03)` | `pnpm audit --audit-level=high` | `pnpm install --frozen-lockfile` |
| Secret scanning (PRs) | `Security supply chain (A03)` | `gitleaks/gitleaks-action` (SHA-pinned) | — |
| Security regression tests | `Backend security tests` | `pytest tests/security` | `uv sync --frozen` |

Dependabot (`.github/dependabot.yml`) opens **weekly grouped** update PRs for
`backend/` (`uv`) and `frontend/` (`npm`).

Third-party GitHub Actions in the supply-chain job are pinned to full commit
SHAs. The `security-supply-chain` CI job is **blocking** (no `continue-on-error`).

### pip-audit allowlist (blocking with documented accepts)

`backend/ci/run-pip-audit.sh` exports `uv.lock` and runs `pip-audit` with
`--ignore-vuln` IDs listed in `backend/ci/pip-audit-allowlist.txt`. Re-verify
on each dependency bump; remove IDs when upstream fixes land.

| Vulnerability ID | Package | Compensating control |
|---|---|---|
| PYSEC-2026-3412 | `weasyprint` | SSRF/LFI mitigated by `app/services/export/weasyprint_safe.py` (LLM10) |
| PYSEC-2026-1325 | `ecdsa` (via `python-jose`) | TalioCV JWTs use HS256 (`AUTH_SECRET`), not ECDSA signing |
| PYSEC-2026-141, 1994, 1996, 1998, 1999 | `urllib3` 1.26.x (via `botocore`) | AWS SDK pin; S3 calls are server-side to trusted AWS endpoints only |

Upgraded in the 2026-08-22 ratchet: `aiohttp`, `cryptography`, `httplib2`,
`boto3`/`botocore` — no remaining allowlist entries for those packages.

### Remaining advisory / operational items

| Scanner | Baseline (2026-08-22) | Owner action |
|---|---|---|
| `pnpm audit --audit-level=high` (frontend) | **Blocking** (2026-08-22): `next@16.2.11`, `next-auth@5.0.0-beta.32`, pnpm overrides for transitive `nanoid`, `postcss`, `sharp`, `js-yaml`, `brace-expansion` | Re-run audit on each frontend dep bump | Ongoing Dependabot |
| `gitleaks detect` (PR) | No confirmed leaks in repo history on 2026-08-21 | Rotate any surfaced credential immediately |
| Container image scan (Trivy) | **N/A** — CI does not build or publish Docker images | Add Trivy when a container build job lands in CI |
| Dependabot grouping | Weekly Monday PRs for backend + frontend | Review and merge grouped updates |

## Security Headers (OWASP A02)

**Last verified:** 2026-08-26  
**Milestone:** M23 Track B post-landing (`feature/m23-track-b-post-landing`); PR #116 landing CSP retained

| Header | Where | Notes |
|---|---|---|
| `Content-Security-Policy` | Next.js proxy (per-request nonce); Caddy API vhost uses `default-src 'none'` | Enforced; production `script-src` uses `'nonce-*'` + `'strict-dynamic'` (no `'unsafe-inline'`); `style-src` keeps `'unsafe-inline'` for React `style={{}}` and scroll-driven landing motion (PR #116) |
| `Strict-Transport-Security` | Next.js (production build only); Caddy (TLS vhosts) | Omitted on local HTTP dev (`:3100`) |
| `X-Content-Type-Options: nosniff` | Next.js + Caddy | — |
| `Referrer-Policy: strict-origin-when-cross-origin` | Next.js + Caddy | — |
| `X-Frame-Options: DENY` + `frame-ancestors 'none'` | Next.js CSP + Caddy | Clickjacking defense |
| `Permissions-Policy` | Next.js + Caddy | Disables unused device APIs; `payment=(self)` for Stripe checkout |

Regression coverage: `frontend/tests/lib/securityHeaders.test.ts`,
`frontend/tests/lib/csp.test.ts` (policy), and `tests/e2e/landing.spec.ts`
(public `/` response headers via proxy nonce CSP).

Before flipping CSP to enforcing mode, run the landing smoke suite:

```bash
cd frontend
PLAYWRIGHT_PORT=3100 E2E_MOCK_API=1 npm run test:e2e:smoke
```

### Accepted-risk baseline (A02 ratchet start)

| Control | Baseline | Owner action | Target blocking date |
|---|---|---|---|
| CSP `style-src 'unsafe-inline'` | Required for M16/M22 landing motion: intro overlay, spotlight, journey rail CSS variables, and PR #116 scroll-linked hero (`HeroScrollExperience` inline `style={{ height: …vh }}`). **Blocker:** CSP Level 3 ignores `'unsafe-inline'` on any directive that also lists a nonce; adding the per-request nonce to `style-src` therefore disables inline `style` attributes and broke the landing page in CI — see `frontend/lib/securityHeaders.ts`. | Prefer hash/nonce per inline block; remove `'unsafe-inline'` in a follow-up ratchet | Ongoing |
| CSP `script-src 'unsafe-inline'` (dev only) | Local dev (`NODE_ENV !== production`) keeps `'unsafe-inline'` + `'unsafe-eval'` with the nonce for Next.js HMR. **Production** enforces nonce + `'strict-dynamic'` only — no `'unsafe-inline'` on `script-src`. | Audit dev-only allowances; keep production ratchet strict | Ongoing |

`style-src 'unsafe-inline'` remains in the **enforcing** production policy until hash/nonce migration. Production `script-src` does **not** include `'unsafe-inline'`.

## Cryptography (OWASP A04)

**Last verified:** 2026-08-22  
**Milestone:** M23 Track B (`feature/owasp-2026-track-b`)

| Control | Implementation | Rotation |
|---|---|---|
| JWT access tokens | HS256 with `AUTH_SECRET`; 15-minute TTL; `typ` claim enforced | Rotate `AUTH_SECRET` — invalidates all outstanding JWTs; force re-login |
| Refresh tokens | Opaque random; SHA-256 digest stored; rotation + reuse detection | Revoked on password reset and concurrent-session replacement |
| BYOK / TOTP at rest | AES-256-GCM via `BYOK_ENCRYPTION_KEY` (32-byte hex) | Deploy new hex key → re-encrypt `User.totp_secret` and any BYOK blobs → retire old key |
| Platform embeddings | OpenAI `text-embedding-3-small`; platform-owned key | Key rotation via secret manager; no user BYOK for embeddings |
| Session cookies | `HttpOnly`, `SameSite=Lax`, `Secure` when `is_production_grade()` | N/A — bound to refresh-token rotation |

Regression coverage: `backend/tests/security/test_crypto_review.py`,
`test_encryption_production_gate.py`, and `test_auth_asvs_l2.py`.

**Accepted risk:** BYOK key rotation is operator-driven (no automatic re-wrap job
yet). Document runbook before first production rotation.

