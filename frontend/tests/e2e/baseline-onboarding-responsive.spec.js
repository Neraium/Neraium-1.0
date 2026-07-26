import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures.js";

const MOBILE_VIEWPORTS = [
  { name: "iPhone Safari width", width: 390, height: 844 },
  { name: "narrow Android width", width: 320, height: 720 },
  { name: "mobile landscape", width: 844, height: 390 },
];

async function openBaselineImport(page, viewport = { width: 390, height: 844 }) {
  await page.setViewportSize(viewport);
  await page.goto("/workspace/data-sources", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  await expect(page.getByRole("heading", { name: "Import Historical Dataset", level: 2 })).toBeVisible();
}

async function chooseSampleDataset(page) {
  await page.getByTestId("csv-upload-input").setInputFiles({
    name: "central-plant-history.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("timestamp,flow,pressure\n2026-07-01T00:00:00Z,10,12\n", "utf8"),
  });
}

test.describe("Baseline onboarding polish", () => {
  test("keeps the copy concise and promotes one stateful primary action", async ({ page }) => {
    await openBaselineImport(page);

    await expect(page.getByRole("heading", { name: "Choose Dataset", level: 3 })).toBeVisible();
    await expect(page.getByText("Import historical telemetry so Neraium can learn how your system normally behaves.")).toBeVisible();
    await expect(page.getByText("Future operation is compared with what Neraium learns here.")).toBeVisible();
    await expect(page.getByText("Awaiting Baseline")).toBeVisible();
    await expect(page.getByText("Historical Dataset", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Choose a Historical Dataset", { exact: true })).toHaveCount(0);
    await expect(page.locator(".upload-analysis-card--baseline .operational-orb")).toHaveCount(0);

    const steps = page.getByRole("list", { name: "Baseline analysis progress" }).getByRole("listitem");
    await expect(steps).toHaveCount(4);
    await expect(steps.nth(0)).toHaveAttribute("aria-current", "step");
    await expect(steps.nth(0)).toContainText("Import");
    await expect(steps.nth(1)).toContainText("Learn");
    await expect(steps.nth(2)).toContainText("Analyze");
    await expect(steps.nth(3)).toContainText("Ready");

    const choose = page.getByRole("button", { name: "Choose Dataset" });
    const formats = page.getByText("View supported formats");
    await expect(choose).toBeVisible();
    await expect(page.getByRole("button", { name: "Start Baseline Analysis" })).toHaveCount(0);
    expect((await choose.boundingBox()).y).toBeLessThan((await formats.boundingBox()).y);

    await chooseSampleDataset(page);
    const start = page.getByRole("button", { name: "Start Baseline Analysis" });
    const replace = page.getByRole("button", { name: "Replace file" });
    await expect(start).toBeVisible();
    await expect(replace).toBeVisible();
    await expect(page.getByText("central-plant-history.csv")).toBeVisible();
    await expect(page.getByText("Ready for Baseline")).toBeVisible();
    await expect(choose).toHaveCount(0);

    const hierarchy = await page.evaluate(() => {
      const primary = document.querySelector(".upload-baseline-card__primary");
      const secondary = document.querySelector(".baseline-file-replace");
      const primaryBox = primary.getBoundingClientRect();
      const secondaryBox = secondary.getBoundingClientRect();
      return {
        primaryWidth: primaryBox.width,
        secondaryWidth: secondaryBox.width,
        primaryBackground: getComputedStyle(primary).backgroundImage,
      };
    });
    expect(hierarchy.primaryWidth).toBeGreaterThan(hierarchy.secondaryWidth);
    expect(hierarchy.primaryBackground).not.toBe("none");
  });

  test("fits the baseline workflow across mobile portrait, narrow, and landscape viewports", async ({ page }) => {
    for (const viewport of MOBILE_VIEWPORTS) {
      await openBaselineImport(page, viewport);

      const initialLayout = await page.evaluate(() => ({
        viewportWidth: innerWidth,
        viewportHeight: innerHeight,
        rootWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        labels: Array.from(document.querySelectorAll(".baseline-import-stepper__label")).map((node) => ({
          text: node.textContent,
          whiteSpace: getComputedStyle(node).whiteSpace,
          clientHeight: node.clientHeight,
          scrollHeight: node.scrollHeight,
        })),
      }));
      expect(initialLayout.rootWidth, viewport.name).toBeLessThanOrEqual(initialLayout.viewportWidth + 1);
      expect(initialLayout.bodyWidth, viewport.name).toBeLessThanOrEqual(initialLayout.viewportWidth + 1);
      expect(initialLayout.labels.map((item) => item.text), viewport.name).toEqual(["Import", "Learn", "Analyze", "Ready"]);
      for (const label of initialLayout.labels) {
        expect(label.whiteSpace, `${viewport.name}: ${label.text}`).toBe("nowrap");
        expect(label.scrollHeight, `${viewport.name}: ${label.text}`).toBeLessThanOrEqual(label.clientHeight + 1);
      }

      await chooseSampleDataset(page);
      const start = page.getByRole("button", { name: "Start Baseline Analysis" });
      await expect(start).toBeVisible();
      const changedControls = await page.evaluate(() => Array.from(document.querySelectorAll(".upload-analysis-card--baseline button, .upload-analysis-card--baseline summary")).map((node) => {
        const box = node.getBoundingClientRect();
        return { label: node.textContent.trim(), left: box.left, right: box.right, top: box.top, bottom: box.bottom, width: box.width, height: box.height };
      }));
      for (const control of changedControls) {
        expect(control.left, `${viewport.name}: ${control.label} left`).toBeGreaterThanOrEqual(0);
        expect(control.right, `${viewport.name}: ${control.label} right`).toBeLessThanOrEqual(viewport.width + 1);
        expect(control.top, `${viewport.name}: ${control.label} top`).toBeGreaterThanOrEqual(0);
        expect(control.bottom, `${viewport.name}: ${control.label} bottom`).toBeLessThanOrEqual(viewport.height + 1);
        expect(control.width, `${viewport.name}: ${control.label} width`).toBeGreaterThanOrEqual(24);
        expect(control.height, `${viewport.name}: ${control.label} height`).toBeGreaterThanOrEqual(24);
      }
    }
  });

  test("preserves keyboard file selection and passes the changed-component accessibility audit", async ({ page }) => {
    await openBaselineImport(page);
    const choose = page.getByRole("button", { name: "Choose Dataset" });
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
    await expect(page.getByRole("button", { name: "Start Baseline Analysis" })).toBeVisible();

    const results = await new AxeBuilder({ page })
      .include(".upload-ops-panel--command")
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    const serious = results.violations.filter((item) => ["serious", "critical"].includes(item.impact));
    expect(serious.map((item) => ({ id: item.id, targets: item.nodes.map((node) => node.target) }))).toEqual([]);
  });
});
