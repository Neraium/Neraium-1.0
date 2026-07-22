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

  test("mobile navigation opens without covering active content after selection", async ({ page }) => {
    await openPortfolio(page, { width: 390, height: 844 });
    const toggle = page.getByRole("button", { name: "Toggle navigation" });
    await toggle.click();
    const navigation = page.getByRole("navigation", { name: "Primary navigation" });
    await expect(navigation).toBeVisible();
    await navigation.getByRole("button", { name: "Site Overview" }).click();
    await expect(page).toHaveURL(/\/sites\/current$/);
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
