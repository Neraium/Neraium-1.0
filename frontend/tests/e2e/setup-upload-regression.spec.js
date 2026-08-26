import { expect, test } from "./fixtures.js";
import { installStoredBaselineUpload } from "./stored-upload-mock.js";

const RETIRED_UPLOAD_REASON = "Retired: app.neraium.com no longer exposes historical file upload as a clean-session production onboarding path.";

async function openBaselineImport(page) {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  await expect(page.getByRole("main", { name: "Neraium operational workspace" })).toBeVisible();
  await page.getByRole("button", { name: "Data", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Establish Initial Baseline", level: 2 })).toBeVisible();
}

async function startStoredBaselineImport(page, { name, csv, jobId, completeWhenPolled = false }) {
  const calls = await installStoredBaselineUpload(page, { jobId, completeWhenPolled });
  await openBaselineImport(page);
  await page.getByTestId("csv-upload-input").setInputFiles({
    name,
    mimeType: "text/csv",
    buffer: Buffer.from(csv, "utf8"),
  });
  await page.getByRole("button", { name: "Continue" }).click();
  return calls;
}

test.describe("Initial baseline upload regression", () => {
  test("opens the baseline import without the retired setup wizard", async ({ page }) => {
    test.skip(true, RETIRED_UPLOAD_REASON);
    await openBaselineImport(page);
    await expect(page.getByTestId("onboarding-root")).toHaveCount(0);
    await expect(page.getByTestId("csv-upload-input")).toBeAttached();
    await expect(page.getByRole("button", { name: "Continue" })).toBeVisible();
  });

  test("file submission enters the current initial-learning workflow", async ({ page }) => {
    test.skip(true, RETIRED_UPLOAD_REASON);
    const calls = await startStoredBaselineImport(page, {
      jobId: "e2e-sample",
      name: "e2e-sample.csv",
      csv: "timestamp,temperature,humidity\n2026-05-01T08:00:00Z,75.2,58\n",
    });

    await expect(page.locator(".baseline-processing-panel")).toBeVisible({ timeout: 30000 });
    await expect(page.getByRole("progressbar", { name: "Validate, stage 2 of 4" })).toBeVisible();
    await expect(page.getByRole("progressbar", { name: "Signal inventory" })).toHaveAttribute("aria-valuenow", "60");
    await expect(page.getByText("6 / 10 signals")).toBeVisible();
    const processingDetails = page.getByRole("button", { name: "Processing details" });
    await expect(processingDetails).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByRole("list", { name: "Detailed backend operations" })).toBeHidden();
    await processingDetails.click();
    await expect(page.getByRole("list", { name: "Detailed backend operations" }).getByText("Unit normalization")).toBeVisible();
    await expect(page.locator("body")).not.toContainText("We hit a workspace error");
    expect(calls.sessions).toBe(1);
    expect(calls.objectPuts).toBe(1);
    expect(calls.completions).toBe(1);
  });

  test("stored CSV transfer completes the canonical baseline workflow", async ({ page }) => {
    const calls = await installStoredBaselineUpload(page, {
      jobId: "stored-baseline",
      filename: "chilled_water_system_data.csv",
      completeWhenPolled: true,
    });
    await page.goto("/baselines/stored-baseline-model/ready", { waitUntil: "domcontentloaded" });

    await expect(page).toHaveURL(/\/baselines\/stored-baseline-model\/ready$/);
    await expect(page.getByTestId("csv-upload-input")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Baseline Established", level: 3 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Waiting for comparison data" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Upload Comparison Dataset" })).toBeVisible();
    await expect(page.locator("body")).not.toContainText("We hit a workspace error");
    expect(calls.sessions).toBe(0);
    expect(calls.objectPuts).toBe(0);
    expect(calls.completions).toBe(0);
    expect(calls.exactBaselineResults).toBeGreaterThanOrEqual(1);
    await expect(page.locator("[aria-label=\"Baseline identity\"]").getByText("stored-baseline-model", { exact: true })).toBeVisible();
  });
});
