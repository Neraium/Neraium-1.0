import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures.js";

async function expectNoSeriousViolations(page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  const violations = results.violations.filter((item) => ["serious", "critical"].includes(item.impact));
  expect(violations.map((item) => ({ id: item.id, targets: item.nodes.map((node) => node.target) }))).toEqual([]);
}

test.describe("Accessibility audit", () => {
  test("skip navigation and primary workspaces work by keyboard", async ({ page }) => {
    await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    const main = page.getByRole("main", { name: "Neraium operational workspace" });
    const skipLink = page.getByRole("link", { name: "Skip to main content" });
    await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeVisible();
    const hiddenStyle = await skipLink.evaluate((node) => {
      const style = getComputedStyle(node);
      return { width: node.getBoundingClientRect().width, clipPath: style.clipPath, overflow: style.overflow };
    });
    expect(hiddenStyle.width).toBeLessThanOrEqual(1);
    expect(hiddenStyle.clipPath === "inset(50%)" || hiddenStyle.overflow === "hidden").toBe(true);
    await page.keyboard.press("Tab");
    await expect(skipLink).toBeFocused();
    expect(await skipLink.evaluate((node) => node.getBoundingClientRect().width)).toBeGreaterThan(1);
    await page.keyboard.press("Enter");
    await expect(main).toBeFocused();
    const connections = page.getByRole("button", { name: "Data", exact: true });
    await connections.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "Establish Initial Baseline", level: 2 })).toBeVisible();
  });

  test("portfolio passes automated serious and critical WCAG rules", async ({ page }) => {
    await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("engineering-reasoning-platform")).toBeVisible();
    await expectNoSeriousViolations(page);
  });

  test("content reflows at narrow and 200-percent-equivalent widths", async ({ page }) => {
    for (const viewport of [{ width: 640, height: 900 }, { width: 320, height: 800 }]) {
      await page.setViewportSize(viewport);
      await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
      const sizes = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth, body: document.body.scrollWidth }));
      expect(sizes.scroll).toBeLessThanOrEqual(sizes.client + 1);
      expect(sizes.body).toBeLessThanOrEqual(sizes.client + 1);
      await expect(page.getByRole("main", { name: "Neraium operational workspace" })).toBeVisible();
    }
  });

  test("reduced-motion preference removes workspace transitions", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
    const duration = await page.locator(".forensic-sidebar").evaluate((node) => getComputedStyle(node).transitionDuration);
    expect(parseFloat(duration || "0")).toBeLessThanOrEqual(0.001);
  });
});
