import { expect, test } from "@playwright/test";

const settingsButtonName = /Open Gate settings|Open workspace menu/i;

test.describe("Neraium frontend smoke", () => {
  test("loads operator shell", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    const settingsButton = page.getByRole("button", { name: settingsButtonName });
    await expect(settingsButton).toBeVisible();
    await expect(page.locator(".system-gate")).toBeVisible();
    await settingsButton.click();
    await expect(page.getByTestId("upload-workspace-entry")).toBeVisible();
  });

  test("mobile settings opens and closes", async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    const settingsButton = page.getByRole("button", { name: settingsButtonName });
    const dataConnectionsButton = page.getByTestId("upload-workspace-entry");
    const closeMenuButton = page.getByRole("button", { name: /Close workspace menu/i });
    await expect(settingsButton).toBeVisible();
    await settingsButton.click();
    await expect(dataConnectionsButton).toBeVisible();
    await closeMenuButton.click();
    await expect(dataConnectionsButton).toBeHidden();

    await context.close();
  });
});
