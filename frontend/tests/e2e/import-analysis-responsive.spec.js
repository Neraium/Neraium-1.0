import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures.js";
import { installStoredBaselineUpload } from "./stored-upload-mock.js";

async function openActiveAnalysis(page) {
  await installStoredBaselineUpload(page, { jobId: "mobile-analysis-preview" });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  await page.getByRole("button", { name: "Import Historical Dataset" }).click();
  await expect(page.getByRole("heading", { name: "Establish Initial Baseline", level: 2 })).toBeVisible();
  await page.getByTestId("csv-upload-input").setInputFiles({
    name: "facility_behavior_history.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("timestamp,temperature\n2026-07-22T08:00:00Z,42.1\n", "utf8"),
  });
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.locator(".baseline-processing-panel")).toBeVisible({ timeout: 30000 });
}

test("active initial learning remains readable and contained on narrow mobile", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openActiveAnalysis(page);

  await expect(page.getByRole("heading", { name: "Validate", level: 3 })).toBeVisible();
  await expect(page.locator(".baseline-processing-panel__header").getByText("Verifying dataset integrity, timestamps, signal consistency, and data quality.", { exact: true })).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Validate, stage 2 of 4" })).toHaveAttribute("aria-valuenow", "2");

  const metrics = await page.evaluate(() => {
    const root = document.documentElement;
    const panel = document.querySelector(".upload-ops-panel--command")?.getBoundingClientRect();
    const card = document.querySelector(".baseline-processing-panel")?.getBoundingClientRect();
    const dataset = document.querySelector(".baseline-processing-panel__dataset")?.getBoundingClientRect();
    const animated = Array.from(document.querySelectorAll(".baseline-learning-visual *"))
      .map((node) => Number.parseFloat(getComputedStyle(node).animationDuration || "0"));
    return {
      overflow: root.scrollWidth - root.clientWidth,
      cardContained: Boolean(panel && card && card.left >= panel.left && card.right <= panel.right),
      datasetContained: Boolean(card && dataset && dataset.left >= card.left && dataset.right <= card.right),
      maxAnimationDuration: Math.max(0, ...animated),
    };
  });
  expect(metrics.overflow).toBeLessThanOrEqual(1);
  expect(metrics.cardContained).toBe(true);
  expect(metrics.datasetContained).toBe(true);
  expect(metrics.maxAnimationDuration).toBeLessThanOrEqual(0.01);

  const results = await new AxeBuilder({ page })
    .include(".upload-ops-panel--command")
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(results.violations.map((violation) => ({ id: violation.id, nodes: violation.nodes.map((node) => ({ target: node.target, html: node.html, summary: node.failureSummary })) }))).toEqual([]);
});
