import { defineConfig, devices } from "@playwright/test"

const nextBin = "node node_modules/next/dist/bin/next"
// Overridable because host :3000 is not always free on a dev workstation
// (Trust/Kia claims it). CI keeps 3000.
const PORT = process.env.PLAYWRIGHT_PORT ?? "3000"
const BASE_URL = `http://localhost:${PORT}`
const webServerCommand = process.env.CI
  ? `${nextBin} start -p ${PORT}`
  : `${nextBin} dev -p ${PORT}`

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  globalSetup: "./tests/e2e/global-setup.mjs",
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: webServerCommand,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: process.env.CI ? 120_000 : 60_000,
    env: {
      NEXTAUTH_SECRET: "playwright-local-secret",
      NEXTAUTH_URL: BASE_URL,
      NEXT_PUBLIC_API_URL: "http://localhost:8000",
      NEXT_PUBLIC_APP_ENV: "local",
      GOOGLE_CLIENT_ID: "playwright-google-client-id",
      GOOGLE_CLIENT_SECRET: "playwright-google-client-secret",
      GITHUB_CLIENT_ID: "playwright-github-client-id",
      GITHUB_CLIENT_SECRET: "playwright-github-client-secret",
    },
  },
})
