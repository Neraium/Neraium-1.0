import { expect, test } from "./fixtures.js";
import { installStoredBaselineUpload } from "./stored-upload-mock.js";

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
    await openBaselineImport(page);
    await expect(page.getByTestId("onboarding-root")).toHaveCount(0);
    await expect(page.getByTestId("csv-upload-input")).toBeAttached();
    await expect(page.getByRole("button", { name: "Continue" })).toBeVisible();
  });

  test("file submission enters the current initial-learning workflow", async ({ page }) => {
    const calls = await startStoredBaselineImport(page, {
      jobId: "e2e-sample",
      name: "e2e-sample.csv",
      csv: "timestamp,temperature,humidity\n2026-05-01T08:00:00Z,75.2,58\n",
    });

    await expect(page.locator(".baseline-processing-panel")).toBeVisible({ timeout: 30000 });
    await expect(page.getByRole("progressbar", { name: "Validate, stage 2 of 4" })).toBeVisible();
    await expect(page.locator("body")).not.toContainText("We hit a workspace error");
    expect(calls.sessions).toBe(1);
    expect(calls.objectPuts).toBe(1);
    expect(calls.completions).toBe(1);
  });

  test("stored CSV transfer completes the canonical baseline workflow", async ({ page }) => {
    const row = "2026-05-01T08:00:00Z,Chilled Water Plant,42.1,58.2,71.4,1.2\n";
    const csv = `timestamp,room,supply_temp,return_temp,pump_speed,flow_rate\n${row.repeat(256)}`;
    const calls = await startStoredBaselineImport(page, {
      jobId: "stored-baseline",
      name: "chilled_water_system_data.csv",
      csv,
      completeWhenPolled: true,
    });

    await expect(page).toHaveURL(/\/baselines\/stored-baseline-model\/ready$/, { timeout: 30000 });
    await expect(page.getByRole("heading", { name: "Baseline Established", level: 3 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Waiting for comparison data" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Upload Comparison Dataset" })).toBeVisible();
    await expect(page.locator("body")).not.toContainText("We hit a workspace error");
    expect(calls.sessions).toBe(1);
    expect(calls.objectPuts).toBe(1);
    expect(calls.completions).toBe(1);
    expect(calls.statusPolls).toBeGreaterThanOrEqual(1);
    expect(calls.baselineResults).toBe(1);
    expect(calls.exactBaselineResults).toBeGreaterThanOrEqual(1);
    await expect(page.locator("[aria-label=\"Baseline identity\"]").getByText("stored-baseline-model", { exact: true })).toBeVisible();
  });
});
