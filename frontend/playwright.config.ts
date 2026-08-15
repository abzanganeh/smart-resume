import { defineConfig, devices } from "@playwright/test"

const nextBin = "node node_modules/next/dist/bin/next"
const webServerCommand = process.env.CI
  ? `${nextBin} start -p 3000`
  : `${nextBin} dev -p 3000`

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
  webServer: {
    command: webServerCommand,
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: process.env.CI ? 120_000 : 60_000,
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
