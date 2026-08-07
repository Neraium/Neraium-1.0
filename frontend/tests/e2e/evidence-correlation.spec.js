import { expect, governedComparisonResult, test } from "./fixtures.js";

function correlationWorkspacePayload() {
  const analysis = {
    systems: [{ id: "hydronic", name: "Chilled Water" }],
    relationships: [{
      id: "pump-flow",
      columns: ["pump_power_kw", "chw_flow_gpm"],
      change_type: "weakened",
      baseline_strength: 0.9,
      current_strength: 0.4,
    }],
    insights: [{
      id: "flow-response",
      title: "Pump response changed",
      confidence: "high",
      system: "Chilled Water",
      what_changed: "Pump power and chilled-water flow no longer follow the learned relationship.",
      why_it_matters: "The persisted relationship changed under comparable operation.",
      variables: ["pump_power_kw", "chw_flow_gpm"],
      supporting_evidence: ["The pump-power and flow relationship weakened."],
      contributing_relationships: [{
        id: "pump-flow",
        columns: ["pump_power_kw", "chw_flow_gpm"],
        change_type: "weakened",
        baseline_strength: 0.9,
        current_strength: 0.4,
      }],
    }],
  };
  const result = governedComparisonResult({
    job_id: "correlation-ui-run",
    facility_name: "North Plant",
    sii_reliable_enough_to_show: true,
    data_quality: { coverage_percent: 100 },
    baseline_analysis: { status: "available", relationship_drift: analysis.relationships },
    analysis_result: analysis,
    analysis_explanation: analysis,
    evidence_package: { id: "package-current" },
  });
  const current = { status: "complete", job_id: result.job_id, result };
  return {
    status: "complete",
    sii_completed: true,
    latest_result: result,
    current_upload: current,
    snapshot: { status: "complete", sii_completed: true, latest_result: result, current_upload: current },
  };
}

async function openEvidenceRecord(page, correlationPayload, viewport) {
  await page.setViewportSize(viewport);
  await page.route("**/api/data/latest-upload**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(correlationWorkspacePayload()),
  }));
  await page.route("**/api/evidence/runs**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ runs: [] }),
  }));
  await page.route("**/api/data/evidence-packages/package-current/related-packages", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(correlationPayload),
  }));
  await page.goto("/evidence/flow-response", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("evidence-record")).toBeVisible();
}

test.describe("Evidence Package Correlation v1", () => {
  test("shows separate related packages with supported reasons and evidence references", async ({ page }) => {
    await openEvidenceRecord(page, {
      correlation_status: "related_packages_found",
      limitations: [],
      related_packages: [{
        relationship_id: "relationship-1",
        package_id: "package-related",
        relationship_type: "evidence_supported_association",
        strongest_supported_relationship: "overlapping_observation_window",
        supporting_relationships: ["overlapping_observation_window", "compatible_operating_context", "same_system"],
        temporal_relationship: "overlapping_observation_window",
        operating_context_relationship: "compatible",
        signal_or_system_overlap: { same_system: true, shared_canonical_signal_ids: [], shared_analytical_pattern_ids: [] },
        evidence_refs: [
          "evidence-package:package-current#operating_context.comparison_window.start",
          "evidence-package:package-related#operating_context.comparison_window.start",
        ],
        limitations: ["canonical_signal_identity_unavailable"],
        provenance: { relationship_rule_version: "evidence-package-correlation-rules/1.0.0", evaluated_from: "immutable_correlation_sources" },
      }],
    }, { width: 1440, height: 900 });

    const related = page.getByTestId("related-evidence");
    await expect(related.getByRole("heading", { name: "Related findings observed" })).toBeVisible();
    await expect(related.getByText("package-current", { exact: true })).toBeVisible();
    await expect(related.getByRole("heading", { name: /Related package package-related/ })).toBeVisible();
    await expect(related.getByText(/overlapping observation windows/)).toBeVisible();
    await related.getByText("Evidence references").click();
    await expect(related.getByText("evidence-package:package-related#operating_context.comparison_window.start")).toBeVisible();
    await expect(related.getByText("Related evidence does not establish cause, propagation, diagnosis, or equipment failure.")).toBeVisible();
  });

  test("preserves an explicit unavailable state without mobile overflow", async ({ page }) => {
    await openEvidenceRecord(page, {
      correlation_status: "unavailable",
      related_packages: [],
      limitations: ["legacy_package_without_correlation_projection"],
    }, { width: 390, height: 844 });

    const related = page.getByTestId("related-evidence");
    await expect(related.getByRole("heading", { name: "Related findings unavailable" })).toBeVisible();
    await expect(related.getByText("This package predates relationship projection.")).toBeVisible();
    const widths = await page.evaluate(() => ({ viewport: innerWidth, root: document.documentElement.scrollWidth, body: document.body.scrollWidth }));
    expect(widths.root).toBeLessThanOrEqual(widths.viewport + 1);
    expect(widths.body).toBeLessThanOrEqual(widths.viewport + 1);
  });
});
