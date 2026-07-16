import { expect, test } from "./fixtures.js";

test.describe("Accessibility audit", () => {
  test("keyboard focus and semantic controls are reachable", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await expect(page.getByRole("main", { name: "Neraium operational workspace" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Primary workflow navigation" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Analyze Historical Telemetry" })).toBeVisible();

    await page.keyboard.press("Tab");
    await expect.poll(async () => page.evaluate(() => {
      const active = document.activeElement;
      return Boolean(active?.matches?.("button, input, select, textarea, a[href], [tabindex]:not([tabindex='-1'])"));
    }), { timeout: 10000 }).toBe(true);
  });

  test("reduced-motion preference is respected", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    const animationDuration = await page.evaluate(() => {
      const node = document.querySelector(".operational-orb__surface");
      if (!node) return null;
      return window.getComputedStyle(node).animationDuration;
    });
    const normalizedDuration = Number.parseFloat(String(animationDuration || "0"));
    expect(normalizedDuration).toBeLessThanOrEqual(0.01);
  });
});
