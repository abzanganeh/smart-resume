import { defineConfig, devices } from "@playwright/test"

const nextBin = "node node_modules/next/dist/bin/next"
// Host :3000 is reserved for Trust/Kia on dev workstations, where
// `reuseExistingServer` will silently adopt whatever already holds the port.
// Set PLAYWRIGHT_PORT (e.g. 3100) to work around it.
//
// The default stays 3000 because 15 specs still hardcode
// `const BASE = "http://localhost:3000"`; they need migrating to relative
// paths before the default can move. landing.spec.ts uses relative paths and
// honours the override today.
const PORT = process.env.PLAYWRIGHT_PORT ?? "3000"
const BASE_URL = `http://localhost:${PORT}`
const webServerCommand = process.env.CI
  ? `${nextBin} start -p ${PORT}`
  : `${nextBin} dev -p ${PORT}`

export default defineConfig({
  testDir: "./tests/e2e",
  // The unsynced-pricing spec needs its own mock fixture and a cleared fetch
  // cache, so it cannot share a run with specs that expect synced prices.
  // `pnpm run test:e2e:pricing-unsynced` sets the flag that opts it in.
  testIgnore:
    process.env.MOCK_PRICES_UNSYNCED === "1"
      ? []
      : ["**/landing-pricing-unsynced.spec.ts"],
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
