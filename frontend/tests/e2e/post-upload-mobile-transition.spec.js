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
  let activeJobId = String(jobId ?? "").trim();
  while (Date.now() - startedAt < timeoutMs) {
    const response = await page.request.get(`http://127.0.0.1:8010/api/data/upload-status/${encodeURIComponent(activeJobId)}`);
    const payload = await response.json().catch(() => ({}));
    const status = String(payload?.status ?? "").toUpperCase();
    if (status === "COMPLETE") return payload;
    if (status === "FAILED") throw new Error(`Upload job ${activeJobId} failed: ${JSON.stringify(payload)}`);
    await page.waitForTimeout(750);
  }
  throw new Error(`Upload job ${activeJobId} did not complete in time.`);
}

async function openUploads(page) {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

  const dataIntakeCard = page.getByRole("button", { name: /Data intake/i });
  if (await dataIntakeCard.isVisible().catch(() => false)) {
    await dataIntakeCard.click();
  } else {
    await page.getByRole("button", { name: /Open Gate settings|Open workspace menu/ }).click();
    const overlay = page.getByTestId("views-overlay");
    if (await overlay.isVisible().catch(() => false)) {
      await overlay.getByRole("button", { name: /Upload CSV \/ Connect Data|Setup & data connections|Data connections/i }).click();
    } else {
      await page.getByRole("button", { name: /Setup & data connections|Data connections|Upload CSV \/ Connect Data/i }).click();
    }
  }

  const uploadTab = page.getByRole("tab", { name: /^Upload( Data)?$/i });
  if (await uploadTab.isVisible().catch(() => false)) {
    await uploadTab.click();
  }
  await expect.poll(async () => {
    const inputVisible = await page.locator("input#csv-upload").isVisible().catch(() => false);
    const processVisible = await page.getByRole("button", { name: /Process Upload/i }).isVisible().catch(() => false);
    return inputVisible && processVisible;
  }, { timeout: 30000, message: "Expected the upload surface to be ready." }).toBe(true);
}

test.describe("Mobile post-upload transition", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("client-side upload transition shows pending or canonical gate state without a blank screen", async ({ page }) => {
    test.setTimeout(180000);
    await openUploads(page);

    const input = page.locator("input#csv-upload");
    await input.setInputFiles({
      name: "mobile-post-upload.csv",
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
    expect(uploadJobId).not.toBe("");

    await expect.poll(async () => page.url(), { timeout: 30000 }).toContain("127.0.0.1:3010");
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    await expect(page.locator("body")).not.toBeEmpty();
    await expect(page.getByText(/No Analysis|Analysis Pending|Telemetry active|No current observations|Behavior Change Detected/i).first()).toBeVisible({ timeout: 30000 });

    await waitForUploadComplete(page, uploadJobId, 180000);

    const gateStatus = page.getByText(/Telemetry active|Analysis Pending|Behavior Change Detected|No current observations/i).first();
    await expect(gateStatus).toBeVisible({ timeout: 30000 });
    await expect(page.getByText(/Evidence confidence/i)).toBeVisible();
    await expect(page.getByText(/Persistence/i)).toBeVisible();
    await expect(page.locator("body")).not.toContainText("We hit a workspace error");
  });
});
