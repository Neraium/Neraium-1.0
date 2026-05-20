import { expect, test } from "@playwright/test";

test.describe("Neraium frontend smoke", () => {
  test("loads operator shell", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    const settingsButton = page.getByRole("button", { name: "Open Gate settings" });
    await expect(settingsButton).toBeVisible();
    await expect(page.locator(".system-gate")).toBeVisible();
    await settingsButton.click();
    await expect(page.getByRole("button", { name: /Setup & data connections|Data connections/i })).toBeVisible();
  });

  test("mobile settings opens and closes", async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    const settingsButton = page.getByRole("button", { name: "Open Gate settings" });
    await expect(settingsButton).toBeVisible();
    await settingsButton.click();
    await expect(page.getByRole("button", { name: /Setup & data connections|Data connections/i })).toBeVisible();
    await settingsButton.click();
    await expect(page.getByRole("button", { name: /Setup & data connections|Data connections/i })).toBeHidden();

    await context.close();
  });
});
