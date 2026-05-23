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

async function waitForUploadComplete(page, jobId, timeoutMs = 120000) {
  const startedAt = Date.now();
  let lastStatus = "";
  let activeJobId = String(jobId ?? "").trim();
  let notFoundCount = 0;
  while (Date.now() - startedAt < timeoutMs) {
    if (!activeJobId) {
      throw new Error("Upload job id is missing.");
    }
    const response = await page.request.get(`http://127.0.0.1:8010/api/data/upload-status/${encodeURIComponent(activeJobId)}`);
    const payload = await response.json().catch(() => ({}));
    const status = String(payload?.status ?? "").toUpperCase();
    if (status) {
      lastStatus = status;
    }
    if (status === "NOT_FOUND") {
      notFoundCount += 1;
      if (notFoundCount >= 3) {
        const latestResponse = await page.request.get("http://127.0.0.1:8010/api/data/latest-upload?include_persisted=1");
        if (latestResponse.ok()) {
          const latestPayload = await latestResponse.json().catch(() => ({}));
          const recoveredJobId = String(
            latestPayload?.latest_result?.job_id
            ?? latestPayload?.history?.[0]?.job_id
            ?? "",
          ).trim();
          if (recoveredJobId && recoveredJobId !== activeJobId) {
            activeJobId = recoveredJobId;
            notFoundCount = 0;
            await page.waitForTimeout(500);
            continue;
          }
        }
      }
      await page.waitForTimeout(750);
      continue;
    }
    if (status === "COMPLETE") {
      return payload;
    }
    if (status === "FAILED") {
      throw new Error(`Upload job ${activeJobId} failed: ${JSON.stringify(payload)}`);
    }
    await page.waitForTimeout(750);
  }
  throw new Error(`Upload job ${activeJobId} did not complete in time. Last status: ${lastStatus || "UNKNOWN"}`);
}

async function openDataConnections(page) {
  const uploadTab = page.getByRole("tab", { name: /^Upload$/i });
  const dataConnectionsHeading = page.getByRole("heading", { name: /^Data Connections$/i });
  const uploadInput = page.locator("input#csv-upload");
  const processUploadButton = page.getByRole("button", { name: /Process Upload/i });
  const directDataConnections = page.getByRole("button", { name: /Setup & data connections|Data connections/i });
  const settingsButton = page.getByRole("button", { name: /Open Gate settings|Gate settings/i });

  const isDataConnectionsReady = async () => {
    const checks = await Promise.all([
      uploadTab.isVisible().catch(() => false),
      dataConnectionsHeading.isVisible().catch(() => false),
      uploadInput.isVisible().catch(() => false),
      processUploadButton.isVisible().catch(() => false),
    ]);
    return checks.some(Boolean);
  };

  const expectDataConnectionsReady = async () => {
    await expect.poll(
      async () => isDataConnectionsReady(),
      { timeout: 30000, message: "Expected Data Connections workspace to be visible." },
    ).toBe(true);
  };

  const hasEntrySignal = async () => {
    const checks = await Promise.all([
      uploadTab.isVisible().catch(() => false),
      dataConnectionsHeading.isVisible().catch(() => false),
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
    await expectDataConnectionsReady();
    return;
  }

  await expect(settingsButton).toBeVisible({ timeout: 30000 });
  await settingsButton.click();
  await page.getByRole("button", { name: /Setup & data connections|Data connections/i }).click();
  await expectDataConnectionsReady();
}

test.describe("Functional verification", () => {
  test("medium upload exposes replay details and replay workspace data", async ({ page }) => {
    test.setTimeout(180000);
    await openDataConnections(page);

    const input = page.locator("input#csv-upload");
    await input.setInputFiles({
      name: "functional-medium.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(buildCsvRows(48), "utf8"),
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

    await waitForUploadComplete(page, uploadJobId, 180000);

    await page.getByRole("button", { name: /Back to Gate/i }).click();
    await expect(page.locator(".system-gate__state")).toBeVisible();

    await page.getByRole("button", { name: "Open Gate settings" }).click();
    await expect(page.getByRole("button", { name: /Data connections/i })).toBeVisible();
  });
});
