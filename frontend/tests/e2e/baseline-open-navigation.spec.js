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
  await expect(page.getByRole("heading", { name: "Initial Baseline Established", level: 3 })).toBeVisible({ timeout: 30000 });
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

test.describe("Open Baseline navigation", () => {
  test("opens the exact completed baseline and browser back restores completion", async ({ page, browserName }) => {
    const errors = captureConsoleErrors(page);
    const navigationLogs = [];
    page.on("console", (message) => {
      if (message.text().includes("baseline navigation")) navigationLogs.push(message.text());
    });
    const exactRequests = [];
    page.on("request", (request) => {
      if (request.url().includes("/api/data/baselines/bdm-v4-04f9195e")) exactRequests.push(request.url());
    });
    await completeBaseline(page);

    await expect(page).toHaveURL(/\/workspace\/data-sources$/);
    const openButton = page.getByRole("button", { name: "Open Baseline" });
    await openButton.scrollIntoViewIfNeeded();
    const hitTargetIsButton = await openButton.evaluate((button) => {
      const rect = button.getBoundingClientRect();
      const topElement = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return topElement === button || button.contains(topElement);
    });
    expect(hitTargetIsButton).toBe(true);

    await openButton.click();
    await expect(page).toHaveURL(/\/portfolio\/default\/baselines\/bdm-v4-04f9195e$/);
    await expect(page.getByRole("heading", { name: "Baseline Details", level: 2 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "bdm-v4-04f9195e", level: 3 })).toBeVisible();
    expect(exactRequests.length).toBeGreaterThanOrEqual(1);
    if (browserName !== "firefox") {
      expect(navigationLogs.some((line) => line.includes("button activated"))).toBe(true);
      expect(navigationLogs.some((line) => line.includes("navigation success"))).toBe(true);
    }

    await page.goBack();
    await expect(page).toHaveURL(/\/workspace\/data-sources$/);
    await expect(page.getByRole("heading", { name: "Initial Baseline Established", level: 3 })).toBeVisible();
    await expect(page.getByRole("button", { name: "Open Baseline" })).toBeEnabled();
    expect(errors).toEqual([]);
  });

  test("refreshes cached completion and opens the selected baseline", async ({ page }) => {
    const errors = captureConsoleErrors(page);
    await completeBaseline(page);
    await page.reload({ waitUntil: "domcontentloaded" });

    await expect(page).toHaveURL(/\/workspace\/data-sources$/);
    await expect(page.getByRole("heading", { name: "Initial Baseline Established", level: 3 })).toBeVisible({ timeout: 30000 });
    await page.getByText("Processing details").click();
    await expect(page.getByText("cache", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Open Baseline" }).click();
    await expect(page).toHaveURL(/\/portfolio\/default\/baselines\/bdm-v4-04f9195e$/);
    await expect(page.getByRole("heading", { name: "bdm-v4-04f9195e", level: 3 })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("preserves native keyboard activation", async ({ page }) => {
    await completeBaseline(page, { jobId: "keyboard-job", modelId: "keyboard-baseline" });
    const openButton = page.getByRole("button", { name: "Open Baseline" });
    await openButton.focus();
    await page.keyboard.press("Enter");

    await expect(page).toHaveURL(/\/portfolio\/default\/baselines\/keyboard-baseline$/);
    await expect(page.getByRole("heading", { name: "keyboard-baseline", level: 3 })).toBeVisible();
  });

  test("loads two exact routes independently and reports a missing baseline", async ({ page }) => {
    const errors = captureConsoleErrors(page);
    await installStoredBaselineUpload(page, { jobId: "job-a", modelId: "baseline-a", filename: "baseline-a.csv" });
    await installStoredBaselineUpload(page, { jobId: "job-b", modelId: "baseline-b", filename: "baseline-b.csv" });

    await page.goto("/portfolio/default/baselines/baseline-a", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "baseline-a", level: 3 })).toBeVisible();
    await expect(page.getByText("baseline-a.csv")).toBeVisible();
    await expect(page.getByText("baseline-b.csv")).toHaveCount(0);

    await page.goto("/portfolio/default/baselines/baseline-b", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "baseline-b", level: 3 })).toBeVisible();
    await expect(page.getByText("baseline-b.csv")).toBeVisible();
    await expect(page.getByText("baseline-a.csv")).toHaveCount(0);
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "baseline-b", level: 3 })).toBeVisible();

    expect(errors).toEqual([]);

    await page.route("**/api/data/baselines/missing-baseline", (route) => route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Baseline was not found." }),
    }));
    await page.goto("/portfolio/default/baselines/missing-baseline", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Baseline Not Found", level: 3 })).toBeVisible();
    await expect(page.getByRole("alert")).toContainText("Baseline missing-baseline was not found in portfolio default.");
  });
});

test.describe("Open Baseline touch activation", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });

  test("opens from a mobile WebKit-compatible tap target", async ({ page }) => {
    const errors = captureConsoleErrors(page);
    await completeBaseline(page, { jobId: "mobile-job", modelId: "mobile-baseline" });
    const openButton = page.getByRole("button", { name: "Open Baseline" });
    await expect(openButton).toBeEnabled();
    await openButton.scrollIntoViewIfNeeded();
    await openButton.tap({ timeout: 15000 });

    await expect(page).toHaveURL(/\/portfolio\/default\/baselines\/mobile-baseline$/);
    await expect(page.getByRole("heading", { name: "mobile-baseline", level: 3 })).toBeVisible();
    expect(errors).toEqual([]);
  });
});
