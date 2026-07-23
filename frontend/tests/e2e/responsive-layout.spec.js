import { expect, test } from "./fixtures.js";

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 }, { name: "laptop", width: 1280, height: 720 },
  { name: "tablet", width: 768, height: 1024 }, { name: "mobile", width: 390, height: 844 },
  { name: "narrow", width: 320, height: 720 }, { name: "landscape", width: 844, height: 390 },
];

async function openPortfolio(page, viewport) {
  await page.setViewportSize(viewport);
  await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("engineering-reasoning-platform")).toBeVisible();
}

test.describe("Responsive engineering workspace", () => {
  test("required viewports avoid horizontal overflow and clipping", async ({ page }) => {
    for (const viewport of VIEWPORTS) {
      await openPortfolio(page, viewport);
      const metrics = await page.evaluate(() => {
        const main = document.querySelector("#forensic-main")?.getBoundingClientRect();
        return { viewport: innerWidth, root: document.documentElement.scrollWidth, body: document.body.scrollWidth, left: main?.left, right: main?.right };
      });
      expect(metrics.root, viewport.name).toBeLessThanOrEqual(metrics.viewport + 1);
      expect(metrics.body, viewport.name).toBeLessThanOrEqual(metrics.viewport + 1);
      expect(metrics.left, viewport.name).toBeGreaterThanOrEqual(0);
      expect(metrics.right, viewport.name).toBeLessThanOrEqual(metrics.viewport + 1);
    }
  });

  test("mobile header keeps a compact menu and flexible search on common widths", async ({ page }) => {
    for (const width of [320, 375, 390, 430]) {
      await openPortfolio(page, { width, height: 844 });
      const menu = page.getByRole("button", { name: "Open menu" });
      await expect(menu).toBeVisible();
      await expect(menu.locator(".forensic-mobile-menu__label")).toBeHidden();
      await expect(menu.locator(".forensic-mobile-menu__icon")).toBeVisible();
      const layout = await page.evaluate(() => {
        const button = document.querySelector(".forensic-mobile-menu").getBoundingClientRect();
        const field = document.querySelector(".global-asset-search").getBoundingClientRect();
        return {
          viewport: innerWidth,
          rootWidth: document.documentElement.scrollWidth,
          button: { left: button.left, right: button.right, top: button.top, width: button.width, height: button.height },
          field: { left: field.left, right: field.right, top: field.top, width: field.width, height: field.height },
        };
      });
      expect(layout.rootWidth, width + "px overflow").toBeLessThanOrEqual(layout.viewport + 1);
      expect(layout.button.width, width + "px menu width").toBeGreaterThanOrEqual(44);
      expect(layout.button.width, width + "px menu width").toBeLessThanOrEqual(48);
      expect(layout.button.height, width + "px menu height").toBe(layout.button.width);
      expect(layout.button.left, width + "px left padding").toBeCloseTo(16, 0);
      expect(layout.viewport - layout.field.right, width + "px right padding").toBeCloseTo(16, 0);
      expect(layout.field.left - layout.button.right, width + "px control gap").toBeGreaterThanOrEqual(8);
      expect(layout.field.left - layout.button.right, width + "px control gap").toBeLessThanOrEqual(12);
      expect(layout.button.top + layout.button.height / 2, width + "px vertical alignment").toBeCloseTo(layout.field.top + layout.field.height / 2, 0);
      expect(layout.field.width, width + "px search width").toBeGreaterThan(0);
    }
  });

  test("wider collapsed header retains the full Menu label", async ({ page }) => {
    await openPortfolio(page, { width: 768, height: 1024 });
    const menu = page.getByRole("button", { name: "Open menu" });
    await expect(menu.locator(".forensic-mobile-menu__label")).toBeVisible();
    await expect(menu.locator(".forensic-mobile-menu__icon")).toBeHidden();
  });

  test("mobile navigation opens without covering active content after selection", async ({ page }) => {
    await openPortfolio(page, { width: 390, height: 844 });
    const toggle = page.getByRole("button", { name: "Open menu" });
    await toggle.click();
    const navigation = page.getByRole("navigation", { name: "Primary navigation" });
    await expect(navigation).toBeVisible();
    await navigation.getByRole("button", { name: "Site Overview" }).click();
    await expect(page).toHaveURL(/\/sites\/[^/]+$/);
    await expect(page.locator(".forensic-sidebar")).not.toHaveClass(/is-open/);
  });

  test("visible touch controls meet the 24-pixel WCAG minimum", async ({ page }) => {
    await openPortfolio(page, { width: 390, height: 844 });
    const undersized = await page.evaluate(() => Array.from(document.querySelectorAll("button, a[href], input, summary")).filter((node) => {
      const style = getComputedStyle(node); const rect = node.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0 && (rect.width < 24 || rect.height < 24);
    }).map((node) => ({ label: node.getAttribute("aria-label") || node.textContent?.trim(), width: node.getBoundingClientRect().width, height: node.getBoundingClientRect().height })));
    expect(undersized).toEqual([]);
  });

  test("long site identifiers truncate without expanding the viewport", async ({ page }) => {
    await openPortfolio(page, { width: 320, height: 720 });
    const search = page.getByRole("combobox", { name: /Search sites/ });
    await search.fill("a-very-long-nonexistent-asset-identifier-that-must-not-expand-the-layout");
    const metrics = await page.evaluate(() => ({ viewport: innerWidth, root: document.documentElement.scrollWidth }));
    expect(metrics.root).toBeLessThanOrEqual(metrics.viewport + 1);
  });
});
