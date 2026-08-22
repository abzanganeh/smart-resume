/**
 * Minimal mock FastAPI for Playwright CI — handles server-side NextAuth login.
 * Browser-initiated API calls are still stubbed per-test via page.route().
 */
import http from "node:http"

const PORT = Number(process.env.MOCK_API_PORT ?? 8000)

function readBody(req) {
  return new Promise((resolve) => {
    let data = ""
    req.on("data", (chunk) => {
      data += chunk
    })
    req.on("end", () => {
      try {
        resolve(data ? JSON.parse(data) : {})
      } catch {
        resolve({})
      }
    })
  })
}

function json(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json" })
  res.end(JSON.stringify(body))
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`)

  if (req.method === "POST" && url.pathname === "/api/auth/login") {
    const body = await readBody(req)
    const email = typeof body.email === "string" ? body.email : "e2e@example.com"
    return json(res, 200, {
      access_token: "mock-ci-access-token",
      token_type: "bearer",
      expires_in: 900,
      user: {
        id: "e2e-user",
        email,
        display_name: "E2E User",
        tier: "paid",
        credit_balance: 0,
        auth_provider: "email",
        email_verified_at: "2026-05-01T00:00:00Z",
        onboarding_completed_at: "2026-05-01T00:00:00Z",
        onboarding_ai_choice: "platform",
        has_totp: false,
        closure_requested_at: null,
        suspended_at: null,
      },
    })
  }

  // Public, unauthenticated endpoints the landing page renders from on the
  // server. page.route() cannot intercept these, so they are served here.
  if (req.method === "GET" && url.pathname === "/api/billing/free-tier") {
    return json(res, 200, { starting_credits: 6 })
  }

  if (req.method === "GET" && url.pathname === "/api/billing/prices") {
    // MOCK_PRICES_UNSYNCED reproduces a fresh environment where PlanConfig
    // rows exist but the Stripe price sync has not run, so every amount is 0.
    const unsynced = process.env.MOCK_PRICES_UNSYNCED === "1"
    return json(res, 200, {
      version: "e2e",
      currency: "USD",
      plans: [
        {
          code: "weekly",
          display_name: "Weekly",
          cycle: "weekly",
          amount_cents: unsynced ? 0 : 999,
          trial_days: null,
          stripe_price_id: "price_e2e_weekly",
          is_active: true,
          features: ["resume_tailor", "job_search"],
          limits: {
            resumes_per_period: 10,
            searches_per_period: 20,
            fit_analyses_per_period: 10,
            whisper_uses_per_period: 2,
            career_watch_companies: 3,
          },
        },
        {
          code: "monthly_pro",
          display_name: "Pro",
          cycle: "monthly",
          amount_cents: unsynced ? 0 : 1999,
          trial_days: null,
          stripe_price_id: "price_e2e_pro",
          is_active: true,
          features: ["resume_tailor", "job_search"],
          limits: {
            resumes_per_period: 50,
            searches_per_period: 100,
            fit_analyses_per_period: 50,
            whisper_uses_per_period: 5,
            career_watch_companies: 10,
          },
        },
        {
          code: "monthly_plus",
          display_name: "Pro+",
          cycle: "monthly",
          amount_cents: unsynced ? 0 : 2999,
          trial_days: null,
          stripe_price_id: "price_e2e_plus",
          is_active: true,
          features: ["resume_tailor"],
          limits: {
            resumes_per_period: 100,
            searches_per_period: 200,
            fit_analyses_per_period: 100,
            whisper_uses_per_period: 15,
            career_watch_companies: 30,
          },
        },
        {
          code: "monthly_premium",
          display_name: "Premium",
          cycle: "monthly",
          amount_cents: unsynced ? 0 : 4999,
          trial_days: null,
          stripe_price_id: "price_e2e_premium",
          is_active: true,
          features: ["resume_tailor"],
          limits: {
            resumes_per_period: 300,
            searches_per_period: 300,
            fit_analyses_per_period: 300,
            whisper_uses_per_period: null,
            career_watch_companies: 50,
          },
        },
      ],
      addons: [],
    })
  }

  if (req.method === "GET" && url.pathname === "/api/auth/me") {
    return json(res, 200, {
      id: "e2e-user",
      email: "e2e@example.com",
      display_name: "E2E User",
      tier: "paid",
      credit_balance: 0,
      auth_provider: "email",
      email_verified_at: "2026-05-01T00:00:00Z",
      onboarding_completed_at: "2026-05-01T00:00:00Z",
      onboarding_ai_choice: "platform",
      has_totp: false,
      closure_requested_at: null,
      suspended_at: null,
    })
  }

  json(res, 404, { detail: "not found" })
})

server.listen(PORT, "127.0.0.1", () => {
  process.stdout.write(`mock-api-server listening on ${PORT}\n`)
})

function shutdown() {
  server.close(() => process.exit(0))
}

process.on("SIGINT", shutdown)
process.on("SIGTERM", shutdown)
