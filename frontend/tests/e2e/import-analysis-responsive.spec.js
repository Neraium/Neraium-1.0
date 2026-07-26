import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures.js";

const ACTIVE_ANALYSIS = {
  job_id: "mobile-analysis-preview",
  status: "PROCESSING",
  processing_state: "accepted",
  worker_state: "active",
  worker_last_update_at: "just now",
  percent: 24,
  progress: 24,
  progress_label: "Preparing analysis...",
  result_available: false,
  status_url: "/api/data/upload-status/mobile-analysis-preview",
};

async function openActiveAnalysis(page) {
  await page.route("**/api/data/upload", (route) => route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(ACTIVE_ANALYSIS) }));
  await page.route("**/api/data/upload-stream/**", (route) => route.fulfill({ status: 404, contentType: "application/json", body: "{}" }));
  await page.route("**/api/data/upload-status/**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ACTIVE_ANALYSIS) }));
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  await page.getByRole("button", { name: "Import Historical Dataset" }).click();
  await expect(page.getByRole("heading", { name: "Import Historical Dataset", level: 2 })).toBeVisible();
  await page.getByTestId("csv-upload-input").setInputFiles({
    name: "facility_behavior_history.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("timestamp,temperature\n2026-07-22T08:00:00Z,42.1\n", "utf8"),
  });
  await page.getByRole("button", { name: "Start Baseline Analysis" }).click();
  await expect(page.locator(".upload-analysis-card--processing")).toBeVisible({ timeout: 30000 });
}

test("active analysis remains readable and contained on narrow mobile", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openActiveAnalysis(page);

  await expect(page.getByText("Validating dataset")).toBeVisible();
  await expect(page.getByText("Checking the dataset format and required signals.")).toBeVisible();
  await expect(page.getByRole("listitem", { name: "Validate: active" })).toBeVisible();

  const metrics = await page.evaluate(() => {
    const root = document.documentElement;
    const panel = document.querySelector(".upload-ops-panel--command")?.getBoundingClientRect();
    const card = document.querySelector(".upload-analysis-card--processing")?.getBoundingClientRect();
    const chip = document.querySelector(".upload-processing-file")?.getBoundingClientRect();
    const animated = Array.from(document.querySelectorAll(".upload-fingerprint-build *"))
      .map((node) => Number.parseFloat(getComputedStyle(node).animationDuration || "0"));
    return {
      overflow: root.scrollWidth - root.clientWidth,
      cardContained: Boolean(panel && card && card.left >= panel.left && card.right <= panel.right),
      chipContained: Boolean(card && chip && chip.left >= card.left && chip.right <= card.right),
      maxAnimationDuration: Math.max(0, ...animated),
    };
  });
  expect(metrics.overflow).toBeLessThanOrEqual(1);
  expect(metrics.cardContained).toBe(true);
  expect(metrics.chipContained).toBe(true);
  expect(metrics.maxAnimationDuration).toBeLessThanOrEqual(0.01);

  const results = await new AxeBuilder({ page })
    .include(".upload-ops-panel--command")
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(results.violations.map((violation) => violation.id)).toEqual([]);
});
