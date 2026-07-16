import { expect, test } from "@playwright/test";

test.describe("Neraium frontend smoke", () => {
  test("loads command center workspace", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await expect(page.getByRole("main", { name: "Neraium operational workspace" })).toBeVisible();
    const commandCenterNav = page
      .getByRole("navigation", { name: "Primary workflow navigation" })
      .getByRole("button", { name: /^Command Center/ });
    await expect(commandCenterNav).toBeVisible();
    await expect(commandCenterNav).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("region", { name: "Operational Status" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Operational Findings" })).toBeVisible();
  });

  test("mobile loads command center workspace", async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await expect(page.getByRole("main", { name: "Neraium operational workspace" })).toBeVisible();
    const commandCenterNav = page
      .getByLabel("Mobile workflow navigation")
      .getByRole("button", { name: /^Command Center/ });
    await expect(commandCenterNav).toBeVisible();
    await expect(commandCenterNav).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("region", { name: "Operational Status" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Operational Findings" })).toBeVisible();

    await context.close();
  });
});
