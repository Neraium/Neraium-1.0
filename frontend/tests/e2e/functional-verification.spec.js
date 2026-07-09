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

async function startCommandCenterUpload(page, { name, csv }) {
  await page.goto("/", { waitUntil: "load" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  await expect(page.getByRole("button", { name: "Analyze New Dataset" })).toBeVisible();

  const uploadAcceptedPromise = page.waitForResponse(
    (response) => response.url().includes("/api/data/upload") && response.request().method() === "POST",
    { timeout: 30000 },
  );
  await page.getByTestId("overview-csv-upload-input").setInputFiles({
    name,
    mimeType: "text/csv",
    buffer: Buffer.from(csv, "utf8"),
  });
  await expect(page.getByTestId("upload-workspace")).toBeVisible({ timeout: 30000 });
  const uploadAccepted = await uploadAcceptedPromise;
  expect(uploadAccepted.ok()).toBeTruthy();
  const uploadPayload = await uploadAccepted.json();
  const uploadJobId = String(uploadPayload?.job_id ?? "").trim();
  expect(uploadJobId.length).toBeGreaterThan(0);
  return uploadJobId;
}

test.describe("Functional verification", () => {
  test("medium upload exposes Operational Fingerprint results and workspace data", async ({ page }) => {
    test.setTimeout(180000);
    const uploadJobId = await startCommandCenterUpload(page, {
      name: "functional-medium.csv",
      csv: buildCsvRows(48),
    });

    await waitForUploadComplete(page, uploadJobId, 180000);
    await expect(page.getByRole("heading", { name: "Analysis Complete" })).toBeVisible({ timeout: 30000 });

    const viewResults = page.getByRole("button", { name: "View Results" });
    if (await viewResults.isVisible().catch(() => false)) {
      await viewResults.click();
    } else {
      await page.getByRole("button", { name: "Back to Workspace" }).click();
    }

    await expect(page.getByRole("main", { name: "Neraium operational workspace" })).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId("operational-orb")).toBeVisible();
    await expect(page.getByRole("button", { name: /Fingerprint/i }).first()).toBeVisible();
  });
});
