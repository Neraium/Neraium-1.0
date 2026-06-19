#!/usr/bin/env node

const { chromium, webkit } = require("playwright");

const APP_URL = (process.env.APP_URL || "https://app.neraium.com").replace(/\/$/, "");
const API_BASE_URL = (process.env.API_BASE_URL || APP_URL).replace(/\/$/, "");
const BROWSER_FLAVOR = String(process.env.BROWSER_FLAVOR || "brave").toLowerCase();
const BROWSER_LABEL = process.env.BROWSER_LABEL || BROWSER_FLAVOR;
const BRAVE_EXECUTABLE_PATH = process.env.BRAVE_EXECUTABLE_PATH || "";
const LOCAL_AUTH_SESSION = process.env.LOCAL_AUTH_SESSION || "";
const LOCAL_AUTH_USER = process.env.LOCAL_AUTH_USER || "operator@facility.com";
const ACCESS_CODE = process.env.NERAIUM_ACCESS_CODE || "";
const TIMEOUT_MS = Number(process.env.SMOKE_BROWSER_TIMEOUT_MS || 180000);
const MOBILE_WIDTH = Number(process.env.SMOKE_MOBILE_WIDTH || 390);
const MOBILE_HEIGHT = Number(process.env.SMOKE_MOBILE_HEIGHT || 844);

function buildCsvRows(count) {
  const lines = ["timestamp,room,flow,pressure,power"];
  const start = Date.parse("2026-05-01T08:00:00Z");
  for (let i = 0; i < count; i += 1) {
    const timestamp = new Date(start + i * 5 * 60_000).toISOString();
    const driftFactor = i > count * 0.6 ? (i - count * 0.6) / (count * 0.4) : 0;
    const flow = (100 - driftFactor * 22 + Math.sin(i / 9) * 1.2).toFixed(3);
    const pressure = (40 + driftFactor * 11 + Math.cos(i / 13) * 0.9).toFixed(3);
    const power = (20 + driftFactor * 7 + Math.sin(i / 11) * 0.7).toFixed(3);
    lines.push(`${timestamp},Pump A,${flow},${pressure},${power}`);
  }
  return `${lines.join("\n")}\n`;
}

function authHeaders() {
  const headers = { Accept: "application/json,*/*" };
  if (ACCESS_CODE) headers["X-Neraium-Access-Code"] = ACCESS_CODE;
  return headers;
}

async function waitForUploadComplete(request, jobId) {
  const deadline = Date.now() + TIMEOUT_MS;
  while (Date.now() < deadline) {
    const response = await request.get(`${API_BASE_URL}/api/data/upload-status/${encodeURIComponent(jobId)}`, { headers: authHeaders() });
    const payload = await response.json().catch(() => ({}));
    const status = String(payload?.status ?? "").toUpperCase();
    if (status === "COMPLETE") return payload;
    if (status === "FAILED") {
      throw new Error(`Upload job ${jobId} failed: ${JSON.stringify(payload)}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`Upload job ${jobId} did not complete in ${TIMEOUT_MS}ms.`);
}

async function launchBrowser() {
  if (BROWSER_FLAVOR === "webkit" || BROWSER_FLAVOR === "safari") {
    return webkit.launch({ headless: true });
  }
  const executablePath = BRAVE_EXECUTABLE_PATH || undefined;
  return chromium.launch({
    channel: executablePath ? undefined : (BROWSER_FLAVOR === "brave" ? "chrome" : undefined),
    executablePath,
    headless: true,
  });
}

async function seedLocalAuth(page) {
  if (!LOCAL_AUTH_SESSION) return;
  await page.addInitScript(({ session, user }) => {
    window.localStorage.setItem(
      "neraium.local_auth.users",
      JSON.stringify([{ email: user, name: "Operator", created_at: "2026-05-21T00:00:00.000Z" }]),
    );
    window.localStorage.setItem("neraium.local_auth.session", session);
  }, { session: LOCAL_AUTH_SESSION, user: LOCAL_AUTH_USER });
}

async function openUploads(page) {
  await page.goto(`${APP_URL}/`, { waitUntil: "load" });
  await page.getByTestId("app-ready-root").waitFor({ state: "visible", timeout: 30000 });
  if (await page.getByTestId("upload-workspace").isVisible().catch(() => false)) {
    return;
  }
  await page.getByTestId("workspace-menu-button").click();
  await page.getByTestId("views-overlay").waitFor({ state: "visible", timeout: 30000 });
  await page.getByTestId("upload-workspace-entry").click();
  await page.getByTestId("process-upload-button").waitFor({ state: "visible", timeout: 30000 });
}

async function main() {
  const browser = await launchBrowser();
  const context = await browser.newContext({ viewport: { width: MOBILE_WIDTH, height: MOBILE_HEIGHT } });
  const page = await context.newPage();
  try {
    await seedLocalAuth(page);
    console.log(`[smoke] browser=${BROWSER_LABEL} app=${APP_URL}`);
    await openUploads(page);

    const input = page.getByTestId("csv-upload-input");
    await input.setInputFiles({
      name: `browser-smoke-${Date.now()}.csv`,
      mimeType: "text/csv",
      buffer: Buffer.from(buildCsvRows(48), "utf8"),
    });

    const uploadAcceptedPromise = page.waitForResponse(
      (response) => response.url().includes("/api/data/upload") && response.request().method() === "POST",
      { timeout: 30000 },
    );
    await page.getByTestId("process-upload-button").click();
    const uploadAccepted = await uploadAcceptedPromise;
    if (!uploadAccepted.ok()) {
      throw new Error(`Upload request failed with status ${uploadAccepted.status()}`);
    }
    const uploadPayload = await uploadAccepted.json();
    const uploadJobId = String(uploadPayload?.job_id ?? "").trim();
    if (!uploadJobId) {
      throw new Error(`Upload response missing job id: ${JSON.stringify(uploadPayload)}`);
    }

    await page.getByTestId("app-ready-root").waitFor({ state: "visible", timeout: 30000 });
    await page.getByText(/No Analysis|Analysis Pending|Telemetry active|No current observations|Behavior Change Detected/i).first().waitFor({ state: "visible", timeout: 30000 });

    await waitForUploadComplete(page.request, uploadJobId);

    await page.getByText(/Telemetry active|Analysis Pending|Behavior Change Detected|No current observations/i).first().waitFor({ state: "visible", timeout: 30000 });
    await page.getByText(/Evidence confidence/i).waitFor({ state: "visible", timeout: 30000 });
    await page.getByText(/Persistence/i).waitFor({ state: "visible", timeout: 30000 });
    const bodyText = await page.locator("body").innerText();
    if (/We hit a workspace error/i.test(bodyText)) {
      throw new Error("Render fallback activated during post-upload transition.");
    }
    console.log(`[smoke] PASS browser=${BROWSER_LABEL} job_id=${uploadJobId}`);
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
  }
}

main().catch((error) => {
  console.error(`[smoke] FAIL browser=${BROWSER_LABEL} error=${error?.message || error}`);
  process.exit(1);
});
