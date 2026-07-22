import { expect, test } from "./fixtures.js";

const RAW_MARKER = "PRODUCTION_RAW_ANALYSIS_DOM_MARKER_";

function oversizedPayload() {
  const analysis = {
    systems: [{ id: "plant", name: "Central plant" }],
    relationships: [{ id: "flow-power", columns: ["chw_flow_gpm", "chiller_power_kw"], change_type: "weakened" }],
    insights: [{ id: "plant-change", title: "Chilled water relationship changed", confidence: "high", system: "Central plant", what_changed: "Chilled water flow and chiller power changed from the learned pattern.", why_it_matters: "The mapped system response changed under comparable conditions.", variables: ["chw_flow_gpm", "chiller_power_kw"], supporting_evidence: ["Flow and power relationship weakened."], contributing_relationships: [{ id: "flow-power", columns: ["chw_flow_gpm", "chiller_power_kw"], change_type: "weakened", hidden_diagnostics: RAW_MARKER.repeat(2000) }] }],
    relationship_graph: { edges: Array.from({ length: 180 }, (_, index) => ({ id: `edge-${index}`, source: "chw_flow_gpm", target: "chiller_power_kw", diagnostics: RAW_MARKER.repeat(100) })) },
  };
  const result = { job_id: "large-run", facility_name: "Central Plant", sii_completed: true, sii_reliable_enough_to_show: true, data_quality: { coverage_percent: 100 }, analysis_result: analysis, analysis_explanation: analysis, baseline_analysis: { status: "available", relationship_drift: analysis.relationships } };
  const current = { status: "complete", job_id: "large-run", result };
  return { status: "complete", sii_completed: true, latest_result: result, current_upload: current, snapshot: { status: "complete", sii_completed: true, latest_result: result, current_upload: current } };
}

async function openSite(page, viewport) {
  await page.setViewportSize(viewport);
  await page.route("**/api/data/latest-upload**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(oversizedPayload()) }));
  await page.goto("/sites/current", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Central Plant" })).toBeVisible();
}

test.describe("Large evidence payload containment", () => {
  for (const viewport of [{ name: "desktop", width: 1440, height: 900 }, { name: "mobile", width: 390, height: 844 }]) {
    test(`${viewport.name} does not expose raw analysis payloads in ordinary workflows`, async ({ page }) => {
      await openSite(page, viewport);
      const metrics = await page.evaluate((marker) => ({ bodyLength: document.body.textContent.length, markerVisible: document.body.textContent.includes(marker), preCount: document.querySelectorAll("pre").length, width: document.documentElement.scrollWidth, viewport: innerWidth }), RAW_MARKER);
      expect(metrics.markerVisible).toBe(false);
      expect(metrics.preCount).toBe(0);
      expect(metrics.bodyLength).toBeLessThan(30000);
      expect(metrics.width).toBeLessThanOrEqual(metrics.viewport + 1);
      await expect(page.getByText("Technical details")).toBeVisible();
      await expect(page.getByText("Scores, identifiers, and processing metadata")).toBeVisible();
    });
  }
});
