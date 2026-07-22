import { expect, test } from "./fixtures.js";

test.describe("Production smoke", () => {
  test("desktop opens the portfolio engineering triage workspace", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    await expect(page.getByRole("main", { name: "Neraium platform workspace" })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Where does the evidence warrant attention/i })).toBeVisible();
    await expect(page.getByRole("button", { name: "Data Connections" })).toBeVisible();
  });

  test("mobile opens compact portfolio navigation without overflow", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("engineering-reasoning-platform")).toBeVisible();
    await expect(page.getByRole("button", { name: "Toggle navigation" })).toBeVisible();
    const metrics = await page.evaluate(() => ({ viewport: innerWidth, root: document.documentElement.scrollWidth, body: document.body.scrollWidth }));
    expect(metrics.root).toBeLessThanOrEqual(metrics.viewport + 1);
    expect(metrics.body).toBeLessThanOrEqual(metrics.viewport + 1);
  });
});
