import { expect, test } from "@playwright/test";

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

async function openDataConnections(page) {
  const uploadTab = page.getByRole("tab", { name: /^Upload$/i });
  const uploadInput = page.locator("input#csv-upload");
  const processUploadButton = page.getByRole("button", { name: /Process Upload/i });
  const directDataConnections = page.getByRole("button", { name: /Setup & data connections|Data connections/i });
  const settingsButton = page.getByRole("button", { name: /Open Gate settings|Gate settings/i });

  const hasEntrySignal = async () => {
    const checks = await Promise.all([
      uploadTab.isVisible().catch(() => false),
      uploadInput.isVisible().catch(() => false),
      processUploadButton.isVisible().catch(() => false),
      directDataConnections.isVisible().catch(() => false),
      settingsButton.isVisible().catch(() => false),
    ]);
    return checks.some(Boolean);
  };

  let entryReady = false;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.goto("/", { waitUntil: "load" });
    await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
    const startedAt = Date.now();
    while (Date.now() - startedAt < 15000) {
      if (await hasEntrySignal()) {
        entryReady = true;
        break;
      }
      await page.waitForTimeout(500);
    }
    if (entryReady) break;
    await page.reload({ waitUntil: "load" }).catch(() => {});
  }
  expect(entryReady).toBe(true);

  if (await uploadTab.isVisible().catch(() => false)) {
    return;
  }
  if (await uploadInput.isVisible().catch(() => false)) {
    return;
  }
  if (await processUploadButton.isVisible().catch(() => false)) {
    return;
  }

  if (await directDataConnections.isVisible().catch(() => false)) {
    await directDataConnections.click();
    await expect(uploadTab).toBeVisible({ timeout: 30000 });
    return;
  }

  await expect(settingsButton).toBeVisible({ timeout: 30000 });
  await settingsButton.click();
  await page.getByRole("button", { name: /Setup & data connections|Data connections/i }).click();
  await expect(uploadTab).toBeVisible({ timeout: 30000 });
}

test.describe("Functional verification", () => {
  test("upload, analysis, gate visibility, reset, and refresh states work end-to-end", async ({ page, request }) => {
    const consoleErrors = [];
    const requestFailures = [];

    page.on("console", (message) => {
      if (["error", "warning"].includes(message.type())) {
        consoleErrors.push(`${message.type()}: ${message.text()}`);
      }
    });
    page.on("requestfailed", (request) => {
      const errorText = request.failure()?.errorText ?? "unknown";
      if (errorText.includes("net::ERR_ABORTED")) return;
      requestFailures.push(`${request.method()} ${request.url()} :: ${errorText}`);
    });

    await openDataConnections(page);

    const input = page.locator("input#csv-upload");
    await input.setInputFiles({
      name: "functional-sample.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(
        "timestamp,room,flow,pressure,power\n"
        + "2026-05-01T08:00:00Z,Pump A,100,40,20\n"
        + "2026-05-01T08:05:00Z,Pump A,100,40,20\n"
        + "2026-05-01T08:10:00Z,Pump A,98,41,21\n"
        + "2026-05-01T08:15:00Z,Pump A,96,43,22\n"
      ),
    });
    await expect(page.getByRole("button", { name: "Process Upload" })).toBeEnabled();
    await page.getByRole("button", { name: "Process Upload" }).click();

    await expect.poll(async () => {
      const response = await request.get("http://127.0.0.1:8010/api/data/latest-upload?include_persisted=1");
      if (!response.ok()) return "request_failed";
      const payload = await response.json();
      return String(payload?.status ?? "unknown").toLowerCase();
    }, { timeout: 120000 }).toBe("active");

    await page.getByRole("button", { name: /Back to Gate/i }).click();
    await expect(page.locator(".system-gate__state")).not.toHaveText(/No Data/i);
    await expect(page.locator(".system-gate__inspect")).toBeVisible();

    await page.locator(".system-gate__center").click();
    await expect(page.getByText(/Gate State Detail|CSV Replay Detail|CSV Analysis Detail/i)).toBeVisible();
    await expect(page.getByText("Replay Frames")).toBeVisible();
    await page.getByRole("button", { name: "Close" }).click();

    await openDataConnections(page);
    await page.getByRole("button", { name: /Reset Everything/i }).click();
    await page.waitForTimeout(1200);
    await page.reload({ waitUntil: "domcontentloaded" });
    const backToGate = page.getByRole("button", { name: /Back to Gate/i });
    if (await backToGate.isVisible().catch(() => false)) {
      await backToGate.click();
    }

    await expect(page.locator(".system-gate__state")).toHaveText(/No Data/i);
    await expect(page.locator(".system-gate__inspect")).toHaveCount(0);

    expect(requestFailures, `Network request failures detected:\n${requestFailures.join("\n")}`).toEqual([]);
    expect(consoleErrors, `Console warnings/errors detected:\n${consoleErrors.join("\n")}`).toEqual([]);
  });

  test("medium upload exposes replay details and replay workspace data", async ({ page, request }) => {
    test.setTimeout(240000);
    await openDataConnections(page);

    const input = page.locator("input#csv-upload");
    await input.setInputFiles({
      name: "functional-medium.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(buildCsvRows(96), "utf8"),
    });
    const processButton = page.getByRole("button", { name: "Process Upload" });
    await expect(processButton).toBeEnabled();
    const uploadAcceptedPromise = page.waitForResponse(
      (response) => response.url().includes("/api/data/upload") && response.request().method() === "POST",
      { timeout: 30000 },
    );
    await processButton.click();
    const uploadAccepted = await uploadAcceptedPromise;
    expect(uploadAccepted.ok()).toBeTruthy();
    const uploadPayload = await uploadAccepted.json();
    const uploadJobId = String(uploadPayload?.job_id ?? "").trim();
    expect(uploadJobId.length).toBeGreaterThan(0);

    await expect.poll(async () => {
      const statusResponse = await request.get(`http://127.0.0.1:8010/api/data/upload-status/${encodeURIComponent(uploadJobId)}`);
      if (!statusResponse.ok()) return "";
      const statusPayload = await statusResponse.json();
      return String(statusPayload?.status ?? "").toLowerCase();
    }, { timeout: 45000 }).toMatch(/pending|active|complete|sii_completed|writing_state|generating_replay|cognition_ready/);

    await page.getByRole("button", { name: /Back to Gate/i }).click();
    await expect(page.locator(".system-gate__state")).toBeVisible();

    await page.getByRole("button", { name: "Open Gate settings" }).click();
    await expect(page.getByRole("button", { name: /Data connections/i })).toBeVisible();
  });
});
