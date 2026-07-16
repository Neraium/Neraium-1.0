import { expect, test } from "@playwright/test";

test.describe("Accessibility audit", () => {
  test("keyboard focus and semantic controls are reachable", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await expect(page.getByRole("main", { name: "Neraium operational workspace" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Primary workflow navigation" })).toBeVisible();
    const commandCenterNav = page
      .getByRole("navigation", { name: "Primary workflow navigation" })
      .getByRole("button", { name: /^Command Center/ });
    await expect(commandCenterNav).toBeVisible();
    await expect(commandCenterNav).toHaveAttribute("aria-current", "page");

    await page.keyboard.press("Tab");
    await expect.poll(async () => page.evaluate(() => {
      const active = document.activeElement;
      return Boolean(active?.matches?.("button, input, select, textarea, a[href], [tabindex]:not([tabindex='-1'])"));
    }), { timeout: 10000 }).toBe(true);
  });

  test("reduced-motion preference is respected", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const page = await context.newPage();
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    const animationDuration = await page.evaluate(() => {
      const node = document.querySelector(".operational-orb__surface");
      if (!node) return null;
      return window.getComputedStyle(node).animationDuration;
    });
    const normalizedDuration = Number.parseFloat(String(animationDuration || "0"));
    expect(normalizedDuration).toBeLessThanOrEqual(0.01);

    await context.close();
  });
});
