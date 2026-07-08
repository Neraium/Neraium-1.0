import { expect, test } from "@playwright/test";

test.describe("Neraium frontend smoke", () => {
  test("loads operational intelligence landing page", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await expect(page.getByRole("heading", { name: "Operational Intelligence for Critical Infrastructure" })).toBeVisible();
    await expect(page.getByLabel("Animated Neraium operational intelligence orb")).toBeVisible();
    await expect(page.getByRole("button", { name: "Launch Workspace" }).first()).toBeVisible();
  });

  test("mobile launches operational workspace from landing page", async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await page.getByRole("button", { name: "Launch Workspace" }).first().click();
    await expect(page.getByRole("heading", { name: "Operational Intelligence" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Analyze New Telemetry" })).toBeVisible();

    await context.close();
  });
});
