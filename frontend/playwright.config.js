import { defineConfig, devices } from "@playwright/test";

const reuseExistingServer = process.env.CI === "true" || process.env.PLAYWRIGHT_REUSE_SERVER === "1";

const backendCommand = [
  "cd ..",
  "PYTHON_BIN=./.venv/bin/python",
  "if [ ! -x \"$PYTHON_BIN\" ]; then PYTHON_BIN=$(command -v python3 || command -v python); fi",
  "PYTHONPATH=backend APP_ENV=test NERAIUM_RUNTIME_DIR=.playwright-runtime NERAIUM_START_BACKGROUND_WORKERS=1 NERAIUM_START_DATA_POLLER=0 \"$PYTHON_BIN\" -m uvicorn app.main:app --host 127.0.0.1 --port 8010",
].join(" && ");

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 90_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:3010",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: [
    {
      command: backendCommand,
      port: 8010,
      timeout: 240_000,
      reuseExistingServer,
    },
    {
      command: "npm run build && npm run preview",
      port: 3010,
      timeout: 240_000,
      reuseExistingServer,
      env: {
        ...process.env,
        VITE_API_BASE_URL: "http://127.0.0.1:8010",
      },
    },
  ],
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
