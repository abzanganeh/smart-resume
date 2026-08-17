import { spawn } from "node:child_process"
import path from "node:path"
import { fileURLToPath } from "node:url"

async function waitForMockServer(port, attempts = 40) {
  for (let i = 0; i < attempts; i += 1) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/auth/me`)
      if (res.ok) return
    } catch {
      // retry
    }
    await new Promise((r) => setTimeout(r, 250))
  }
  throw new Error(`Mock API server did not start on port ${port}`)
}

export default async function globalSetup() {
  if (!process.env.CI) return

  const dir = path.dirname(fileURLToPath(import.meta.url))
  const script = path.join(dir, "mock-api-server.mjs")
  const mockServer = spawn(process.execPath, [script], {
    stdio: "inherit",
    env: { ...process.env, MOCK_API_PORT: "8000" },
  })

  mockServer.on("error", (err) => {
    console.error("mock-api-server failed:", err)
  })

  await waitForMockServer(8000)

  return async () => {
    if (!mockServer.killed) {
      mockServer.kill("SIGTERM")
    }
  }
}
