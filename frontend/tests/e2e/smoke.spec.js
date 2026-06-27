import { expect, test } from "@playwright/test";

test.describe("Neraium frontend smoke", () => {
  test("loads current operator overview shell", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await expect(page.getByRole("heading", { name: /Overview|Health/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Start with telemetry" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Upload CSV|Analyze System|Upload Data/i })).toBeVisible();
  });

  test("mobile opens upload workspace from overview", async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await page.getByRole("button", { name: /Upload CSV|Analyze System|Upload Data/i }).click();
    await expect(page.getByTestId("upload-workspace")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Analyze System" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Choose Telemetry File/i })).toBeVisible();

    await context.close();
  });
});
