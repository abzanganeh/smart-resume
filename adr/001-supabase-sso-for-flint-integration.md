# ADR-001: Supabase SSO for TalioCV + Flint

| Field | Value |
|-------|-------|
| Status | **Accepted** |
| Date | 2026-06-04 |
| Deciders | Product / engineering |
| Context | Strategy B integration — shared billing, extension auth, post-interview digest sync |

## Context

Flint and TalioCV serve the same job-seeker journey but today use **different auth systems**:

| Product | Auth today | Identity store |
|---------|------------|----------------|
| **Flint** (desktop) | Supabase GoTrue | `auth.users` via Supabase |
| **TalioCV** (web) | Custom HS256 JWT (`AUTH_SECRET`, python-jose) | Postgres `users` + `refresh_tokens` |

Strategy B Phase 3 requires:

- One subscription (`flint_access`) gates both products
- Extension, web, and desktop must resolve the **same user id**
- Post-interview digest sync must attach to the correct TalioCV account
- No permanent dual-auth bridge (Redis handoff tokens are for Phase 1 import only, not identity)

Three options were considered:

1. **Token exchange** — TalioCV issues short-lived cross-product tokens; Flint redeems for a session. Lower migration cost; permanent integration surface.
2. **Supabase SSO for both** — TalioCV migrates to GoTrue; Flint unchanged. Single identity; higher upfront migration cost.
3. **Dual independent auth** — Phase 1 Redis bridge only. Blocks shared billing and creates long-term ops debt.

## Decision

**Migrate TalioCV to Supabase GoTrue.** Flint keeps its existing Supabase auth implementation.

Both products authenticate against the **same Supabase project** (or linked projects with identical `auth.users` if multi-tenant separation is required later).

Phase 1 cross-product handoff (`POST /api/sessions/{id}/flint-handoff` → `flint://import`) remains **token-based and auth-agnostic** — it does not depend on this ADR and ships first.

## Consequences

### Positive

- Single `user_id` (Supabase UUID) across web, extension, and desktop
- `flint_access` entitlement is a simple column / plan flag on one user record
- Extension can use Supabase OAuth / PKCE instead of maintaining a parallel JWT refresh path
- Flint `start_session` entitlement check uses the same JWT Flint already stores in the OS keychain
- Eliminates long-term token-exchange service and dual refresh-token rotation

### Negative

- TalioCV must migrate off HS256 JWT + `refresh_tokens` table (2–3 weeks in Phase 3)
- NextAuth v5 config in `frontend/auth.ts` must be rewired to Supabase provider
- Existing users need a one-time migration (email match → `auth.users`)
- Local dev requires Supabase CLI (or shared dev project) for TalioCV, not only `AUTH_SECRET`

### Neutral

- Admin auth (`ADMIN_JWT_ALG`) remains separate — admin panel is not in Strategy B scope
- Phase 1 Redis handoff tokens are unchanged; they carry `user_id` from whichever auth system is active at export time

## Implementation outline (Phase 3)

### TalioCV backend

1. Add `supabase-py` / GoTrue client; validate Supabase JWT on protected routes.
2. Feature flag `USE_SUPABASE_AUTH` (default `false` in dev until migration complete).
3. New dependency `get_current_user_supabase` parallel to existing `get_current_user`; switch routers behind flag.
4. Deprecate `backend/app/services/auth/tokens.py` HS256 access JWT issuance once flag is default-on.
5. Migration script: for each `users.email`, create or link `auth.users` row; store `supabase_user_id` on `users` table.
6. Refresh-token rotation in `refresh_tokens` table retired for Supabase sessions (GoTrue handles refresh).

### TalioCV frontend

1. Replace NextAuth credentials provider with Supabase Auth (or Supabase-backed NextAuth adapter).
2. Session cookie carries Supabase access token instead of `backendAccessToken` HS256 JWT.
3. Update `frontend/lib/api.ts` `Authorization: Bearer` header source.

### Flint

- No auth migration — already Supabase.
- Phase 3 adds `EntitlementChecker` calling TalioCV `GET /api/user/entitlements` with the Supabase JWT.

### Chrome extension (Phase 2 → 3 transition)

- **Phase 2 MVP:** may use existing TalioCV `/api/auth/login` JWT until Phase 3 lands.
- **Phase 3:** migrate extension to Supabase OAuth PKCE flow (recommended for MV3 + public client).

## Rollback

- `USE_SUPABASE_AUTH=false` reverts API to HS256 JWT path.
- Keep `refresh_tokens` table and `tokens.py` until 30 days after full cutover with zero rollback incidents.
- Do not delete `AUTH_SECRET` from config until rollback window closes.

## Security requirements

- Supabase anon key in frontend only; service role key **never** in browser or extension bundle
- RLS on all TalioCV Postgres tables unchanged; `auth.uid()` becomes canonical user reference
- No session content (JD, resume text) in handoff or entitlement logs at INFO+
- API keys remain in OS keychain (Flint) — unchanged

## Out of scope

- Merging Postgres schemas between products
- Flint moving off Supabase
- Admin panel SSO (separate ADR if needed)

## Related

- Strategy B plan: Phase 1 (link), Phase 3 (billing + this ADR)
- ADR-002 (extension ↔ desktop IPC): deep link for Phase 2; native messaging deferred
- ADR-003 (backend unification trigger): write before Phase 5/6

## Acceptance criteria (Phase 3 gate)

- [ ] New TalioCV signup creates `auth.users` row
- [ ] Existing user login resolves same `user_id` on web and Flint
- [ ] `GET /api/user/entitlements` returns `flint_access` for Supabase JWT
- [ ] Extension auth uses Supabase flow
- [ ] `USE_SUPABASE_AUTH=true` in staging for 1 week with no rollback
