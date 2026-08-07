import AxeBuilder from "@axe-core/playwright";

import { expect, test } from "./fixtures.js";
import { installStoredBaselineUpload } from "./stored-upload-mock.js";


const ingestionSummary = {
  contract_version: "historical-ingestion-trust/v1",
  dataset_id: "historical-review-mobile",
  dataset_identity: "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
  revision: 1,
  readiness: { outcome: "ready_with_limitations", limitations: ["One flow unit remains unresolved."] },
  signal_counts: {
    detected: 12,
    confidently_mapped: 9,
    need_review: 1,
    excluded: 2,
    unit_conflicts: 1,
    duplicate_candidates: 1,
    timestamp_gaps: 2,
    configuration_boundaries: 1,
  },
};

const ingestionProfile = {
  ...ingestionSummary,
  summary: ingestionSummary,
  signal_profiles: [{
    canonical_signal_id: "sig-flow",
    source_column: "Loop Flow",
    proposed_canonical_role: "flow",
  }],
  review: {
    state: "review_required",
    items: [
      { type: "unit", signal_id: "sig-flow", source_column: "Loop Flow", reason: "Unit evidence needs review." },
      { type: "timestamp", signal_id: null, source_column: "Timestamp", reason: "Two gaps were preserved without interpolation." },
    ],
  },
  trust_dimensions: [
    { dimension: "timestamp_integrity", status: "medium", reasons: ["Two gaps were preserved without interpolation."] },
    { dimension: "unit_confidence", status: "review_required", reasons: ["One unit is unresolved."] },
  ],
};

test.describe("Historical ingestion review", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("surfaces only focused uncertainty in the completed mobile upload flow", async ({ page }) => {
    await installStoredBaselineUpload(page, {
      jobId: "historical-review-mobile",
      completeWhenPolled: true,
      ingestionTrust: ingestionSummary,
    });
    await page.route("**/api/data/ingestion/v1/datasets/historical-review-mobile", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(ingestionProfile),
    }));

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    await page.getByRole("button", { name: "Import Historical Dataset" }).click();
    await page.getByTestId("csv-upload-input").setInputFiles({
      name: "historical-review-mobile.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("Timestamp,Loop Flow\n2026-05-01T08:00:00Z,100\n", "utf8"),
    });
    await page.getByRole("button", { name: "Continue" }).click();

    await expect(page).toHaveURL(/\/baselines\/historical-review-mobile-model\/ready$/, { timeout: 30000 });
    await expect(page.getByRole("heading", { name: "Ready with documented limitations" })).toBeVisible();
    await expect(page.getByLabel("Ingestion trust summary")).toContainText("12");
    await expect(page.getByLabel("Confirmed source unit for Loop Flow")).toBeVisible();
    await expect(page.getByRole("button", { name: "Save Review Decisions" })).toBeDisabled();

    const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(horizontalOverflow).toBeLessThanOrEqual(1);
    const accessibility = await new AxeBuilder({ page }).include(".historical-review").analyze();
    expect(accessibility.violations).toEqual([]);
  });
});
