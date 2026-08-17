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
