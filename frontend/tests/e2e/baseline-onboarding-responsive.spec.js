import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures.js";

const MOBILE_VIEWPORTS = [
  { name: "iPhone Safari width", width: 390, height: 844 },
  { name: "narrow Android width", width: 320, height: 720 },
  { name: "mobile landscape", width: 844, height: 390 },
];

async function openBaselineImport(page, viewport = { width: 1440, height: 900 }) {
  await page.setViewportSize(viewport);
  await page.goto("/workspace/data-sources", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  await expect(page.getByRole("heading", { name: "Establish Initial Baseline", level: 2 })).toBeVisible();
}

async function chooseSampleDataset(page) {
  await page.getByTestId("csv-upload-input").setInputFiles({
    name: "central-plant-history.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("timestamp,flow,pressure\n2026-07-01T00:00:00Z,10,12\n", "utf8"),
  });
}

test.describe("Initial baseline learning experience", () => {
  test("makes Neraium's learning philosophy and one primary action immediately clear", async ({ page }) => {
    await openBaselineImport(page);

    await expect(page.getByText("Upload historical operating data so Neraium can establish its initial understanding of how your infrastructure behaves.")).toBeVisible();
    await expect(page.getByText("This dataset becomes Neraium's first learned operating model.")).toBeVisible();
    await expect(page.getByText(/discovers persistent relationships between signals instead of memorizing static thresholds/i)).toBeVisible();
    await expect(page.getByText(/normal only evolves when new operating behavior is persistent and verified/i)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Teach Neraium from normal operation", level: 3 })).toBeVisible();

    const steps = page.getByRole("list", { name: "How Neraium establishes its initial baseline" }).getByRole("listitem");
    await expect(steps).toHaveCount(5);
    await expect(steps).toHaveText([
      "1Historical Dataset",
      "2Validate Data Integrity",
      "3Learn Operating Relationships",
      "4Establish Initial Baseline",
      "5Continuous Learning Begins",
    ]);

    const choose = page.getByRole("button", { name: /choose historical dataset/i });
    await expect(choose).toBeVisible();
    await expect(page.getByRole("button", { name: "Establish Initial Baseline" })).toHaveCount(0);
    await expect(page.getByText("Supported data sources")).toBeVisible();
    await expect(page.getByText("Compare", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Evidence", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Findings", { exact: true })).toHaveCount(0);

    await chooseSampleDataset(page);
    const establish = page.getByRole("button", { name: "Establish Initial Baseline" });
    const replace = page.getByRole("button", { name: "Replace file" });
    await expect(establish).toBeVisible();
    await expect(replace).toBeVisible();
    await expect(page.getByText("central-plant-history.csv")).toBeVisible();
    await expect(page.getByRole("button", { name: "Analyze New Data" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Extend Baseline" })).toHaveCount(0);

    const hierarchy = await page.evaluate(() => {
      const primary = document.querySelector(".upload-baseline-card__primary");
      const secondary = document.querySelector(".baseline-file-replace");
      const primaryBox = primary.getBoundingClientRect();
      const secondaryBox = secondary.getBoundingClientRect();
      return {
        primaryWidth: primaryBox.width,
        secondaryWidth: secondaryBox.width,
        primaryHeight: primaryBox.height,
      };
    });
    expect(hierarchy.primaryWidth).toBeGreaterThan(hierarchy.secondaryWidth);
    expect(hierarchy.primaryHeight).toBeGreaterThanOrEqual(44);
  });

  test("has no horizontal overflow and keeps touch controls usable across mobile sizes", async ({ page }) => {
    for (const viewport of MOBILE_VIEWPORTS) {
      await openBaselineImport(page, viewport);
      await chooseSampleDataset(page);

      const layout = await page.evaluate(() => {
        const controls = Array.from(document.querySelectorAll(".upload-analysis-card--baseline button, .upload-analysis-card--baseline summary")).map((node) => {
          const box = node.getBoundingClientRect();
          return {
            label: node.textContent.trim(),
            left: box.left,
            right: box.right,
            width: box.width,
            height: box.height,
          };
        });
        return {
          viewportWidth: innerWidth,
          rootWidth: document.documentElement.scrollWidth,
          bodyWidth: document.body.scrollWidth,
          controls,
        };
      });

      expect(layout.rootWidth, viewport.name).toBeLessThanOrEqual(layout.viewportWidth + 1);
      expect(layout.bodyWidth, viewport.name).toBeLessThanOrEqual(layout.viewportWidth + 1);
      for (const control of layout.controls) {
        expect(control.left, `${viewport.name}: ${control.label} left`).toBeGreaterThanOrEqual(0);
        expect(control.right, `${viewport.name}: ${control.label} right`).toBeLessThanOrEqual(viewport.width + 1);
        expect(control.width, `${viewport.name}: ${control.label} width`).toBeGreaterThanOrEqual(24);
        expect(control.height, `${viewport.name}: ${control.label} height`).toBeGreaterThanOrEqual(34);
        expect(control.height, `${viewport.name}: ${control.label} height`).toBeLessThanOrEqual(60);
      }
    }
  });

  test("supports keyboard file selection and passes the changed-component accessibility audit", async ({ page }) => {
    await openBaselineImport(page);
    const choose = page.getByRole("button", { name: /choose historical dataset/i });
    await choose.focus();
    await expect(choose).toBeFocused();
    const chooserPromise = page.waitForEvent("filechooser");
    await page.keyboard.press("Enter");
    const chooser = await chooserPromise;
    await chooser.setFiles({
      name: "keyboard-history.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("timestamp,value\n2026-07-01T00:00:00Z,1\n", "utf8"),
    });
    await expect(page.getByRole("button", { name: "Establish Initial Baseline" })).toBeVisible();

    const results = await new AxeBuilder({ page })
      .include(".upload-ops-panel--command")
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    const serious = results.violations.filter((item) => ["serious", "critical"].includes(item.impact));
    expect(serious.map((item) => ({ id: item.id, targets: item.nodes.map((node) => node.target) }))).toEqual([]);
  });
});
