import { expect, test } from "./fixtures.js";

test.describe("Retired Live Monitoring production boundary", () => {
  test("normal production navigation does not advertise the legacy workspace", async ({ page }) => {
    await page.goto("/portfolio", { waitUntil: "domcontentloaded" });

    await expect(page.getByRole("button", { name: "Live Monitoring" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Data", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Connect a data source" })).toBeVisible();
  });

  test("a legacy direct route fails closed into the Operations Brief", async ({ page }) => {
    await page.goto("/workspace/live-monitoring", { waitUntil: "domcontentloaded" });

    await expect(page).toHaveURL(/\/sites\/current$/);
    await expect(page.getByTestId("live-monitoring-workspace")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Connect a data source" })).toBeVisible();
  });
});
