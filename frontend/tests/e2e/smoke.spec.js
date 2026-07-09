import { expect, test } from "@playwright/test";

test.describe("Neraium frontend smoke", () => {
  test("loads command center workspace", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await expect(page.getByRole("main", { name: "Neraium operational workspace" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Command Center" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Operational Fingerprint Pending" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Analyze Historical Data" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Connect Live Data" })).toBeVisible();
  });

  test("mobile loads command center workspace", async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await expect(page.getByRole("main", { name: "Neraium operational workspace" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Command Center Overview" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Command Center" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Analyze Historical Data" })).toBeVisible();

    await context.close();
  });
});
