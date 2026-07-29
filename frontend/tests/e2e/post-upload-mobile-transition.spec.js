import { expect, test } from "./fixtures.js";
import { installStoredBaselineUpload } from "./stored-upload-mock.js";

test.describe("Mobile post-upload transition", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("stored baseline completion shows canonical success without a blank screen", async ({ page }) => {
    const calls = await installStoredBaselineUpload(page, { jobId: "mobile-post-upload", completeWhenPolled: true });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    await page.getByRole("button", { name: "Import Historical Dataset" }).click();
    await expect(page.getByRole("heading", { name: "Establish Initial Baseline", level: 2 })).toBeVisible();
    await page.getByTestId("csv-upload-input").setInputFiles({
      name: "mobile-post-upload.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("timestamp,flow,pressure\n2026-05-01T08:00:00Z,100,40\n", "utf8"),
    });
    await page.getByRole("button", { name: "Continue" }).click();

    await expect(page.getByRole("heading", { name: "Initial Baseline Established", level: 3 })).toBeVisible({ timeout: 30000 });
    await expect(page.getByRole("button", { name: "Open Baseline" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Import Comparison Dataset" })).toBeVisible();
    await expect(page.locator("body")).not.toContainText("We hit a workspace error");
    expect(calls.sessions).toBe(1);
    expect(calls.objectPuts).toBe(1);
    expect(calls.completions).toBe(1);
    expect(calls.statusPolls).toBeGreaterThanOrEqual(1);
    expect(calls.baselineResults).toBe(1);
  });
});
