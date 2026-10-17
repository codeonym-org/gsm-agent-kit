import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  retries: 0,
  timeout: 35_000,
  expect: { timeout: 12_000 },
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
      : {},
  },
  webServer: [
    {
      command: "pnpm realtime",
      url: "http://127.0.0.1:3002",
      env: { GSM_API_PROXY_TARGET: "http://127.0.0.1:8765", GSM_REALTIME_PORT: "3002" },
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "uv run --project ../.. --no-sync python ../../tests/e2e/console_backend.py",
      url: "http://127.0.0.1:8765/__fixture__/ready",
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "pnpm exec vite preview --host 127.0.0.1 --port 4173",
      url: "http://127.0.0.1:4173",
      env: {
        GSM_API_PROXY_TARGET: "http://127.0.0.1:8765",
        GSM_REALTIME_PROXY_TARGET: "http://127.0.0.1:3002",
      },
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
