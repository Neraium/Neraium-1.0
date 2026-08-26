import { expect, test } from "./fixtures.js";
import { installStoredBaselineUpload } from "./stored-upload-mock.js";

test.describe("Mobile stored-baseline transition", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("an exact stored baseline shows canonical success without a blank screen", async ({ page }) => {
    const calls = await installStoredBaselineUpload(page, { jobId: "mobile-post-upload", completeWhenPolled: true });
    await page.goto("/baselines/mobile-post-upload-model/ready", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    await expect(page).toHaveURL(/\/baselines\/mobile-post-upload-model\/ready$/);
    await expect(page.getByTestId("csv-upload-input")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Baseline Established", level: 3 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Waiting for comparison data" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Upload Comparison Dataset" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Return to Portfolio" })).toBeVisible();
    await expect(page.locator("body")).not.toContainText("We hit a workspace error");
    expect(calls.sessions).toBe(0);
    expect(calls.objectPuts).toBe(0);
    expect(calls.completions).toBe(0);
    expect(calls.exactBaselineResults).toBeGreaterThanOrEqual(1);
  });
});
