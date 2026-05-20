import { expect, test } from "@playwright/test";

test.describe("Accessibility audit", () => {
  test("keyboard focus and semantic controls are reachable", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Open Gate settings" })).toBeFocused();

    await page.keyboard.press("Enter");
    await expect(page.getByRole("button", { name: /Setup & data connections|Data connections/i })).toBeVisible();
  });

  test("reduced-motion preference is respected", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const page = await context.newPage();
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    const animationDuration = await page.evaluate(() => {
      const node = document.querySelector(".system-gate");
      if (!node) return null;
      return window.getComputedStyle(node).animationDuration;
    });
    const normalizedDuration = Number.parseFloat(String(animationDuration || "0"));
    expect(normalizedDuration).toBeLessThanOrEqual(0.01);

    await context.close();
  });
});
