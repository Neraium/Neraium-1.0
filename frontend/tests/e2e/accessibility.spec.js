import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures.js";

async function expectNoWcagViolations(page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  const details = results.violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact,
    help: violation.help,
    targets: violation.nodes.map((node) => node.target.join(" ")),
  }));
  expect(details, JSON.stringify(details, null, 2)).toEqual([]);
}

test.describe("Accessibility audit", () => {
  test("skip navigation and critical command-center controls work by keyboard", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    const main = page.getByRole("main", { name: "Neraium platform workspace" });
    const skipLink = page.getByRole("button", { name: "Skip to main content" });
    await expect(main).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Primary workflow navigation" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Operational Status" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Import and Analyze Dataset" })).toBeVisible();

    await page.keyboard.press("Tab");
    await expect(skipLink).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(main).toBeFocused();

    await page.keyboard.press("Tab");
    await expect.poll(async () => page.evaluate(() => {
      const active = document.activeElement;
      return Boolean(active?.matches?.("button, input, select, textarea, a[href], summary, [tabindex]:not([tabindex='-1'])"));
    }), { timeout: 10000 }).toBe(true);

    const dataSourcesButton = page.getByRole("button", { name: /Datasets & Connectors/ });
    await dataSourcesButton.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "Import and Analyze a Dataset" })).toBeVisible();
  });

  test("command center, data sources, and home pass automated WCAG rules", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    await expectNoWcagViolations(page);

    await page.getByRole("button", { name: /Datasets & Connectors/ }).click();
    await expect(page.getByRole("heading", { name: "Import and Analyze a Dataset" })).toBeVisible();
    await expectNoWcagViolations(page);

    const homePage = await page.context().newPage();
    await homePage.goto("/home", { waitUntil: "domcontentloaded" });
    await expect(homePage.getByTestId("home-page")).toBeVisible();
    await expectNoWcagViolations(homePage);
    await homePage.close();
  });

  test("content reflows at a 200-percent equivalent and a narrow viewport", async ({ page }) => {
    await page.setViewportSize({ width: 640, height: 900 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
    await expect(page.getByRole("heading", { name: "Operational Status" })).toBeVisible();

    await page.setViewportSize({ width: 320, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
    await expect(page.getByRole("main", { name: "Neraium platform workspace" })).toBeVisible();
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
