import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures.js";
import { installStoredBaselineUpload } from "./stored-upload-mock.js";

async function openBaselineImport(page) {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  await page.getByRole("button", { name: "Data", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Establish Initial Baseline", level: 2 })).toBeVisible();
}

test("queued baseline reconciles truthfully after refresh and leaves a recoverable new-upload path", async ({ page }) => {
  const jobId = "refresh-queued-baseline";
  const calls = await installStoredBaselineUpload(page, {
    jobId,
    filename: "production-baseline.csv",
    latestWhileProcessing: true,
    processingOverrides: {
      status: "PENDING",
      processing_state: "queued",
      execution_state: "queued",
      queue_state: "pending",
      worker_state: "running",
      worker_claimed: false,
      percent: 10,
      progress: 10,
      progress_label: "Baseline construction queued",
      propagation_label: "Baseline construction queued",
    },
  });
  const pollingStarts = [];
  page.on("console", (message) => {
    if (message.text().includes("telemetry job polling started")) pollingStarts.push(message.text());
  });

  await openBaselineImport(page);
  await page.getByTestId("csv-upload-input").setInputFiles({
    name: "production-baseline.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("timestamp,flow,power\n2026-08-08T00:00:00Z,42,18\n", "utf8"),
  });
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.locator(".baseline-processing-panel")).toBeVisible({ timeout: 30000 });
  await expect(page.locator(".backend-progress").getByText("Queued · waiting for worker claim")).toBeVisible();
  expect(calls.sessions).toBe(1);
  expect(calls.completions).toBe(1);

  pollingStarts.length = 0;
  const pollsBeforeRefresh = calls.statusPolls;
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  if (await page.getByRole("heading", { name: "Establish Initial Baseline", level: 2 }).count() === 0) {
    await page.getByRole("button", { name: "Data", exact: true }).click();
  }

  await expect(page.locator(".baseline-processing-panel")).toBeVisible();
  await expect(page.locator(".baseline-processing-panel__dataset").getByText("production-baseline.csv", { exact: true })).toBeVisible();
  const restoredProgress = page.locator(".backend-progress");
  await expect(restoredProgress.getByText("Queued · waiting for worker claim")).toBeVisible();
  await expect(restoredProgress.getByText("Signal inventory", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/Analysis active/i)).toHaveCount(0);
  expect(await page.getByTestId("csv-upload-input").evaluate((input) => input.files?.length ?? -1)).toBe(0);
  await expect.poll(() => calls.statusPolls).toBeGreaterThan(pollsBeforeRefresh);
  await expect.poll(() => pollingStarts.length).toBe(1);
  expect(calls.sessions).toBe(1);
  expect(calls.objectPuts).toBe(1);
  expect(calls.completions).toBe(1);

  await page.setViewportSize({ width: 390, height: 844 });
  const layout = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(layout.scrollWidth).toBeLessThanOrEqual(layout.clientWidth + 1);
  const accessibility = await new AxeBuilder({ page })
    .include(".upload-ops-panel--command")
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(accessibility.violations.map((violation) => ({
    id: violation.id,
    targets: violation.nodes.map((node) => node.target),
  }))).toEqual([]);

  const startAnother = page.getByRole("button", { name: "Start another upload" });
  await startAnother.focus();
  await expect(startAnother).toBeFocused();
  await Promise.all([
    page.waitForEvent("filechooser"),
    page.keyboard.press("Enter"),
  ]);
  await expect(page.getByRole("heading", { name: "Upload historical data" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "production-baseline.csv" })).toBeVisible();
  await expect(page.getByText("Status:").locator("..")).toContainText("Queued");
  await expect(page.getByRole("button", { name: "View active job" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Dismiss job" })).toBeVisible();
  expect(calls.sessions).toBe(1);
  expect(calls.objectPuts).toBe(1);
  expect(calls.completions).toBe(1);
});
