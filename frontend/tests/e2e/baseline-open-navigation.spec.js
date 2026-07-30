import { expect, test } from "./fixtures.js";
import { installStoredBaselineUpload } from "./stored-upload-mock.js";

async function openBaselineImport(page) {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  const dataButton = page.getByRole("button", { name: "Data", exact: true });
  if (await dataButton.isVisible()) await dataButton.click();
  else await page.getByRole("button", { name: "Import Historical Dataset" }).click();
  await expect(page.getByRole("heading", { name: "Establish Initial Baseline", level: 2 })).toBeVisible();
}

async function completeBaseline(page, options = {}) {
  const jobId = options.jobId ?? "04f9195e381b4d82b6b6285d3c58185f";
  const modelId = options.modelId ?? "bdm-v4-04f9195e";
  const calls = await installStoredBaselineUpload(page, {
    jobId,
    modelId,
    filename: options.filename ?? "baseline-production.csv",
    completeWhenPolled: true,
  });
  await openBaselineImport(page);
  await page.getByTestId("csv-upload-input").setInputFiles({
    name: options.filename ?? "baseline-production.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("timestamp,flow,pressure\n2026-07-29T00:00:00Z,100,40\n", "utf8"),
  });
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(new RegExp(`/baselines/${modelId}/ready$`), { timeout: 30000 });
  await expect(page.getByRole("heading", { name: "Baseline Established", level: 3 })).toBeVisible();
  return { calls, jobId, modelId };
}

function captureConsoleErrors(page) {
  const errors = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

test.describe("Baseline-ready navigation", () => {
  test("automatically opens the exact completed baseline without rendering analysis findings", async ({ page }) => {
    const errors = captureConsoleErrors(page);
    const exactRequests = [];
    page.on("request", (request) => {
      if (request.url().includes("/api/data/portfolios/default/baselines/bdm-v4-04f9195e")) exactRequests.push(request.url());
    });

    await completeBaseline(page);

    await expect(page.getByRole("heading", { name: "Waiting for comparison data" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Upload Comparison Dataset" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Return to Portfolio" })).toBeVisible();
    await expect(page.getByText(/items in review|being monitored|Known operational change|Unassigned Analysis/i)).toHaveCount(0);
    expect(exactRequests.length).toBeGreaterThanOrEqual(1);
    expect(errors).toEqual([]);
  });

  test("refresh restores the canonical baseline-ready state", async ({ page }) => {
    const errors = captureConsoleErrors(page);
    await completeBaseline(page);
    await page.reload({ waitUntil: "domcontentloaded" });

    await expect(page).toHaveURL(/\/baselines\/bdm-v4-04f9195e\/ready$/);
    await expect(page.getByRole("heading", { name: "Baseline Established", level: 3 })).toBeVisible({ timeout: 30000 });
    await expect(page.getByRole("heading", { name: "Waiting for comparison data" })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("ignores a stale legacy latest analysis while opening an exact baseline", async ({ page }) => {
    const staleLatestResult = {
      job_id: "fac4f77516d643f880adf70301260597",
      run_id: "fac4f77516d643f880adf70301260597",
      dataset_id: "fac4f77516d643f880adf70301260597",
      portfolio_id: "default",
      system_id: "default",
      workflow: "legacy_analysis",
      status: "COMPLETE",
      processing_state: "complete",
      sii_completed: true,
      filename: "commercial water system.csv",
      conditions: [{
        id: "condition-pumping-system-5c07679cd8",
        headline: "Connected relationships strengthening in Pumping System",
        affected_signals: ["pump_vibration_mms", "ct_outlet_temp_f", "differential_pressure_psi"],
      }],
    };
    await installStoredBaselineUpload(page, {
      jobId: "baseline-only-job",
      modelId: "bdm-v5-d5556684",
      filename: "resort chw baseline.csv",
      staleLatestResult,
    });

    await page.goto("/baselines/bdm-v5-d5556684/ready", { waitUntil: "domcontentloaded" });

    await expect(page.getByRole("heading", { name: "Baseline Established", level: 3 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Waiting for comparison data" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Upload Comparison Dataset" })).toBeVisible();
    await expect(page.getByText(/Pumping System|pump_vibration_mms|Unassigned Analysis/i)).toHaveCount(0);
  });

  test("primary action opens the canonical comparison upload route", async ({ page }) => {
    await completeBaseline(page, { jobId: "keyboard-job", modelId: "keyboard-baseline" });
    const comparisonButton = page.getByRole("button", { name: "Upload Comparison Dataset" });
    await comparisonButton.focus();
    await page.keyboard.press("Enter");

    await expect(page).toHaveURL(/\/baselines\/keyboard-baseline\/comparisons\/new$/);
    await expect(page.getByRole("heading", { name: "Import Comparison Dataset", level: 2 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Baseline Established" })).toHaveCount(0);
  });

  test("loads two exact ready routes independently and reports a missing baseline", async ({ page }) => {
    const errors = captureConsoleErrors(page);
    await installStoredBaselineUpload(page, { jobId: "job-a", modelId: "baseline-a", filename: "baseline-a.csv" });
    await installStoredBaselineUpload(page, { jobId: "job-b", modelId: "baseline-b", filename: "baseline-b.csv" });

    await page.goto("/baselines/baseline-a/ready", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Baseline Established", level: 3 })).toBeVisible();
    await expect(page.getByText("baseline-a.csv")).toBeVisible();
    await expect(page.getByText("baseline-b.csv")).toHaveCount(0);

    await page.goto("/baselines/baseline-b/ready", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Baseline Established", level: 3 })).toBeVisible();
    await expect(page.getByText("baseline-b.csv")).toBeVisible();
    await expect(page.getByText("baseline-a.csv")).toHaveCount(0);
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Baseline Established", level: 3 })).toBeVisible();

    expect(errors).toEqual([]);

    await page.route("**/api/data/portfolios/default/baselines/missing-baseline", (route) => route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Baseline was not found." }),
    }));
    await page.goto("/baselines/missing-baseline/ready", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Baseline Not Found", level: 3 })).toBeVisible();
    await expect(page.getByRole("alert")).toContainText("Baseline missing-baseline was not found in portfolio default.");
  });
});

test.describe("Baseline-ready touch activation", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });

  test("opens comparison upload from a mobile tap target", async ({ page }) => {
    const errors = captureConsoleErrors(page);
    await completeBaseline(page, { jobId: "mobile-job", modelId: "mobile-baseline" });
    const comparisonButton = page.getByRole("button", { name: "Upload Comparison Dataset" });
    await expect(comparisonButton).toBeEnabled();
    await comparisonButton.scrollIntoViewIfNeeded();
    await comparisonButton.tap({ timeout: 15000 });

    await expect(page).toHaveURL(/\/baselines\/mobile-baseline\/comparisons\/new$/);
    await expect(page.getByRole("heading", { name: "Import Comparison Dataset", level: 2 })).toBeVisible();
    expect(errors).toEqual([]);
  });
});
