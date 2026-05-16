import { expect, test } from "@playwright/test";

// Temporarily disabled while the Playwright smoke suite is paused.
test.describe.skip("Neraium frontend smoke", () => {
  test("loads cultivation-first operator shell", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByLabel("Workspace navigation").getByText("NERAIUM // OPS")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Cultivation Mission Control" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Expert Mode Off|Expert Mode On/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Sample Off|Sample On/i })).toBeVisible();
  });

  test("mobile menu opens and closes", async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    await page.goto("/");

    const menuButton = page.getByRole("button", { name: /Menu/i });
    await expect(menuButton).toBeVisible();
    await menuButton.click();
    await expect(page.locator("aside.workspace-drawer")).toHaveClass(/workspace-drawer--open/);

    await page.getByRole("button", { name: /Close/i }).click();
    await expect(page.locator("aside.workspace-drawer")).not.toHaveClass(/workspace-drawer--open/);

    await context.close();
  });
});
