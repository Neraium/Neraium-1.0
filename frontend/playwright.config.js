import { defineConfig, devices } from "@playwright/test";

const backendPort = Number(process.env.PLAYWRIGHT_BACKEND_PORT || 8012);
const frontendPort = Number(process.env.PLAYWRIGHT_FRONTEND_PORT || 3012);
const reuseExistingServer = process.env.PLAYWRIGHT_REUSE_SERVER === "1";
const externalServer = process.env.PLAYWRIGHT_EXTERNAL_SERVER === "1";
const pythonBin = process.platform === "win32" ? "python" : "../.venv/bin/python";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 150_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: externalServer ? undefined : [
    {
      command: `${pythonBin} ../scripts/start_e2e_backend.py`,
      port: backendPort,
      timeout: 240_000,
      reuseExistingServer,
      env: {
        ...process.env,
        PLAYWRIGHT_BACKEND_PORT: String(backendPort),
        PLAYWRIGHT_FRONTEND_PORT: String(frontendPort),
      },
    },
    {
      command: `npm run build && npm run preview -- --port ${frontendPort}`,
      port: frontendPort,
      timeout: 240_000,
      reuseExistingServer,
      env: { ...process.env, VITE_API_BASE_URL: `http://127.0.0.1:${backendPort}` },
    },
  ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
