import { expect, test } from "./fixtures.js";
import { installStoredBaselineUpload } from "./stored-upload-mock.js";

test.describe("Initial baseline upload regression", () => {
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
