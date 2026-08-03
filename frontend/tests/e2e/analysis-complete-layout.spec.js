import { expect, governedComparisonResult, test } from "./fixtures.js";

function evidenceLimitedPayload() {
  const analysis = { systems: [{ name: "Hydronic loop" }], relationships: [{ id: "flow-demand", columns: ["flow", "demand"], change_type: "weakened" }], insights: [{ id: "limited", title: "Possible hydraulic restriction", confidence: "high", system: "Hydronic loop", what_changed: "Flow response weakened under comparable demand.", why_it_matters: "The relationship change may reflect subsystem behavior.", recommended_check: "Inspect Filter-03", variables: ["flow", "demand"], supporting_evidence: ["Flow relationship changed."], contributing_relationships: [{ id: "flow-demand", columns: ["flow", "demand"], change_type: "weakened" }] }] };
  const result = governedComparisonResult({ job_id: "limited-run", facility_name: "Limited Site", sii_completed: true, sii_reliable_enough_to_show: true, data_quality: { coverage_percent: 30, warnings: ["Historian X unavailable"] }, data_gaps: [{ source: "Historian X", duration: "4 hours", signals: ["flow"], overlaps_change_window: true }], analysis_result: analysis, analysis_explanation: analysis, baseline_analysis: { status: "available", relationship_drift: analysis.relationships } });
  const current = { status: "complete", job_id: "limited-run", result };
  return { status: "complete", sii_completed: true, latest_result: result, current_upload: current, snapshot: { status: "complete", sii_completed: true, latest_result: result, current_upload: current } };
}

async function openSite(page, viewport) {
  await page.setViewportSize(viewport);
  await page.route("**/api/data/latest-upload**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(evidenceLimitedPayload()) }));
  await page.goto("/sites/current", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("workspace-state-insufficientEvidence")).toBeVisible();
}

test.describe("Evidence-limited analysis presentation", () => {
  test("withholds unsupported findings and explains the evidence boundary", async ({ page }) => {
    await openSite(page, { width: 1440, height: 900 });
    await expect(page.getByText("Operations Brief · Insufficient Evidence")).toBeVisible();
    await expect(page.getByRole("heading", { name: "More evidence is needed" })).toBeVisible();
    await expect(page.getByText("Analysis completed, but the available data does not support a reliable finding.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Review Evidence" })).toBeVisible();
    await expect(page.getByText("Possible hydraulic restriction")).toHaveCount(0);
    await expect(page.getByText("Inspect Filter-03")).toHaveCount(0);
  });

  test("mobile preserves the evidence boundary without overflow", async ({ page }) => {
    await openSite(page, { width: 390, height: 844 });
    await expect(page.getByRole("heading", { name: "More evidence is needed" })).toBeVisible();
    await expect(page.getByText("Possible hydraulic restriction")).toHaveCount(0);
    const widths = await page.evaluate(() => ({ root: document.documentElement.scrollWidth, body: document.body.scrollWidth, viewport: innerWidth }));
    expect(widths.root).toBeLessThanOrEqual(widths.viewport + 1);
    expect(widths.body).toBeLessThanOrEqual(widths.viewport + 1);
  });
});
