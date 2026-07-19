import { expect, test } from "./fixtures.js";

const RAW_MARKER = "PRODUCTION_RAW_ANALYSIS_DOM_MARKER_";

function productionOversizedLatestUploadPayload() {
  const relationshipGraph = {
    nodes: [
      { id: "chw_flow_gpm", label: "Chilled water flow" },
      { id: "chiller_power_kw", label: "Chiller power" },
    ],
    edges: Array.from({ length: 180 }, (_, index) => ({
      id: "redacted-edge-" + index,
      source: "chw_flow_gpm",
      target: "chiller_power_kw",
      description: RAW_MARKER.repeat(220),
      statistics: { baseline_strength: 0.77, current_strength: 0.06, correlation_delta: 0.83 },
    })),
  };
  const analysis = {
    analysis_id: "production-shaped-analysis",
    source_file: "redacted-production-upload.csv",
    generated_at: "2026-07-19T06:00:00Z",
    data_quality: { warnings: [] },
    executive_summary: {
      overall_operational_status: "Current behavior changed",
      highest_priority_finding: "Chilled water relationship shifted",
      recommended_action: "Check pump schedule and valve position",
    },
    systems: [{ id: "central-plant", name: "Central plant" }],
    relationships: [{ id: "relationship-0", columns: ["chw_flow_gpm", "chiller_power_kw"], change_type: "weakened" }],
    fingerprint: { status: "changed", meaning: "The operating fingerprint shifted.", evidence_refs: ["ev-1"] },
    insights: [{
      id: "central-plant-shift",
      title: "Chilled water relationship shifted",
      severity: "high",
      confidence: "high",
      confidence_score: 0.91,
      system: "Central plant",
      what_changed: "Chilled water flow and chiller power stopped moving together like the baseline window.",
      recommended_check: "Check pump schedule and valve position",
      contributing_relationships: [{ id: "relationship-0", columns: ["chw_flow_gpm", "chiller_power_kw"], change_type: "weakened" }],
      evidence_refs: ["ev-1"],
    }],
    evidence_index: {
      "ev-1": {
        evidence_id: "ev-1",
        type: "relationship_change",
        description: "Chilled water flow and chiller power relationship weakened.",
        supporting_signals: ["Flow decreased 9%", "Power increased 14%"],
        source_columns: ["chw_flow_gpm", "chiller_power_kw"],
        confidence: "high",
        confidence_score: 0.91,
      },
    },
    relationship_graph: relationshipGraph,
  };
  const result = {
    job_id: "production-shaped-job",
    filename: "redacted-production-upload.csv",
    processed_at: "2026-07-19T06:00:00Z",
    row_count: 5856,
    sii_reliable_enough_to_show: true,
    sii_completed: true,
    analysis_result: analysis,
    analysis,
    analysis_explanation: analysis,
    baseline_analysis: {
      status: "available",
      relationship_graph: relationshipGraph,
      relationship_drift: analysis.relationships,
    },
    relationship_model: { relationship_graph: relationshipGraph },
    sii_intelligence: {
      facility_state: "needs review",
      baseline: { state: "changed", confidence: 0.82 },
      telemetry_integrity: {
        enabled: true,
        status: "good",
        signal_integrity: Array.from({ length: 120 }, (_, index) => ({
          signal_id: "redacted_signal_" + index,
          source_id: "redacted-production-upload.csv",
          completeness: 1,
          samples_expected: 5856,
          samples_received: 5856,
          notes: RAW_MARKER.repeat(80),
        })),
      },
    },
  };
  const currentUpload = {
    job_id: "production-shaped-job",
    filename: "redacted-production-upload.csv",
    status: "complete",
    result,
  };
  const snapshot = {
    status: "complete",
    session_state: "verified",
    sii_completed: true,
    processed_at: "2026-07-19T06:00:00Z",
    current_upload: currentUpload,
    latest_result: result,
    history: [{ job_id: "production-shaped-history", result }],
  };
  return {
    session_state: "verified",
    status: "complete",
    sii_completed: true,
    processed_at: "2026-07-19T06:00:00Z",
    latest_result: result,
    latestResult: result,
    current_result: result,
    current_upload: currentUpload,
    snapshot,
  };
}

async function routeOversizedLatestUpload(page) {
  const payload = productionOversizedLatestUploadPayload();
  await page.route("**/api/data/latest-upload**", (route) => {
    const origin = route.request().headers().origin ?? "*";
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: {
        "access-control-allow-origin": origin,
        "access-control-allow-credentials": "true",
      },
      body: JSON.stringify(payload),
    });
  });
}

async function openCommandCenterWithPayload(page, viewport) {
  await page.setViewportSize(viewport);
  await routeOversizedLatestUpload(page);
  await page.goto("/workspace", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  await expect(page.getByRole("heading", { name: "Operational Fingerprint Summary" })).toBeVisible();
}

async function analysisRecordDomMetrics(page) {
  return page.evaluate((marker) => {
    const record = Array.from(document.querySelectorAll("details"))
      .find((details) => details.querySelector("summary")?.textContent.trim() === "Analysis Record");
    const preview = document.querySelector("[data-testid='analysis-record-preview']");
    return {
      bodyTextLength: document.body.textContent.length,
      recordTextLength: record?.textContent.length ?? 0,
      previewTextLength: preview?.textContent.length ?? 0,
      hiddenPreCount: document.querySelectorAll("details:not([open]) pre.advanced-json").length,
      largePreCount: Array.from(document.querySelectorAll("pre.advanced-json")).filter((node) => node.textContent.length > 5000).length,
      markerVisible: document.body.textContent.includes(marker.repeat(8)),
      recordOpen: Boolean(record?.open),
    };
  }, RAW_MARKER);
}

test.describe("Command Center oversized analysis record", () => {
  test("desktop production build keeps the closed Analysis Record out of the DOM", async ({ page }) => {
    await openCommandCenterWithPayload(page, { width: 1440, height: 900 });
    const closed = await analysisRecordDomMetrics(page);
    expect(closed.recordOpen).toBe(false);
    expect(closed.recordTextLength).toBe("Analysis Record".length);
    expect(closed.hiddenPreCount).toBe(0);
    expect(closed.largePreCount).toBe(0);
    expect(closed.markerVisible).toBe(false);

    await page.getByText("Analysis Record", { exact: true }).click();
    await expect(page.getByTestId("analysis-record-preview")).toBeVisible();
    const opened = await analysisRecordDomMetrics(page);
    expect(opened.previewTextLength).toBeLessThanOrEqual(5000);
    expect(opened.largePreCount).toBe(0);
    expect(opened.bodyTextLength).toBeLessThan(90000);
  });

  test("mobile production build renders Command Center with the closed oversized record", async ({ page }) => {
    await openCommandCenterWithPayload(page, { width: 390, height: 844 });
    await expect(page.getByRole("button", { name: /Command Center/i }).first()).toBeVisible();
    const closed = await analysisRecordDomMetrics(page);
    expect(closed.recordOpen).toBe(false);
    expect(closed.hiddenPreCount).toBe(0);
    expect(closed.largePreCount).toBe(0);
    expect(closed.markerVisible).toBe(false);
    expect(closed.bodyTextLength).toBeLessThan(90000);
  });
});
