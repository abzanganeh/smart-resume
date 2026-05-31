import { defineConfig, devices } from "@playwright/test"

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Start Next.js dev server before running tests if PLAYWRIGHT_LIVE is not set
  webServer: {
    command: "pnpm dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: {
      NEXTAUTH_SECRET: "playwright-local-secret",
      NEXTAUTH_URL: "http://localhost:3000",
      NEXT_PUBLIC_API_URL: "http://localhost:8000",
      NEXT_PUBLIC_APP_ENV: "local",
      GOOGLE_CLIENT_ID: "playwright-google-client-id",
      GOOGLE_CLIENT_SECRET: "playwright-google-client-secret",
      GITHUB_CLIENT_ID: "playwright-github-client-id",
      GITHUB_CLIENT_SECRET: "playwright-github-client-secret",
    },
  },
})
