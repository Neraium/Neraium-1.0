import { expect, test } from "./fixtures.js";

const apiBaseURL = `http://127.0.0.1:${Number(process.env.PLAYWRIGHT_BACKEND_PORT || 8012)}`;

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
  let activeJobId = String(jobId ?? "").trim();
  while (Date.now() - startedAt < timeoutMs) {
    const response = await page.request.get(`${apiBaseURL}/api/data/upload-status/${encodeURIComponent(activeJobId)}`);
    const payload = await response.json().catch(() => ({}));
    const status = String(payload?.status ?? "").toUpperCase();
    if (status === "COMPLETE") return payload;
    if (status === "FAILED") throw new Error(`Upload job ${activeJobId} failed: ${JSON.stringify(payload)}`);
    await page.waitForTimeout(750);
  }
  throw new Error(`Upload job ${activeJobId} did not complete in time.`);
}

async function startCommandCenterUpload(page, { name, csv }) {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  await expect(page.getByRole("main", { name: "Neraium operational workspace" })).toBeVisible();

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
  expect(uploadJobId).not.toBe("");
  return uploadJobId;
}

test.describe("Mobile post-upload transition", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("client-side upload transition shows pending or canonical workspace state without a blank screen", async ({ page }) => {
    test.setTimeout(180000);
    const uploadJobId = await startCommandCenterUpload(page, {
      name: "mobile-post-upload.csv",
      csv: buildCsvRows(48),
    });

    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    await expect(page.locator("body")).not.toContainText("We hit a workspace error");

    await waitForUploadComplete(page, uploadJobId, 180000);
    await expect(page.locator("body")).not.toContainText("We hit a workspace error");

    const completionFallback = page.getByRole("button", { name: "Open Command Center" });
    const commandCenter = page.getByRole("main", { name: "Neraium operational workspace" });
    await expect(completionFallback.or(commandCenter).first()).toBeVisible({ timeout: 30000 });
    await expect(page.locator("body")).not.toContainText("We hit a workspace error");
  });
});
