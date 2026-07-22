import { expect, test } from "./fixtures.js";

const analysis = {
  systems: [{ id: "pump", name: "Pump system" }],
  relationships: [{ id: "pump-flow", columns: ["pump_power", "flow"], change_type: "weakened" }],
  insights: [{ id: "pump-change", title: "Pump relationship changed", confidence: "high", system: "Pump system", what_changed: "Pump power and flow stopped moving together like the learned baseline.", why_it_matters: "The mapped response changed under comparable conditions.", recommended_check: "Review pump power and flow trends.", variables: ["pump_power", "flow"], supporting_evidence: ["Pump power and flow relationship weakened."], contributing_relationships: [{ id: "pump-flow", columns: ["pump_power", "flow"], change_type: "weakened" }] }],
};
const result = { job_id: "pump-run", facility_name: "Pump Site", sii_completed: true, sii_reliable_enough_to_show: true, data_quality: { coverage_percent: 100 }, analysis_result: analysis, analysis_explanation: analysis, baseline_analysis: { status: "available", relationship_drift: analysis.relationships } };
const upload = { status: "complete", job_id: "pump-run", result };
const payload = { status: "complete", sii_completed: true, latest_result: result, current_upload: upload, snapshot: { status: "complete", sii_completed: true, latest_result: result, current_upload: upload } };

async function openInvestigation(page, viewport) {
  await page.setViewportSize(viewport);
  await page.route("**/api/data/latest-upload**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) }));
  await page.goto("/investigations/pump-change", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("dialog", { name: /pump_power/i })).toBeVisible();
}

test.describe("Evidence Drawer responsive behavior", () => {
  test("desktop keeps graph, timeline, and evidence visible together", async ({ page }) => {
    await openInvestigation(page, { width: 1440, height: 900 });
    await expect(page.getByRole("heading", { name: "Behavioral constellation" })).toBeVisible();
    await expect(page.getByRole("slider", { name: /Relationship comparison time/ })).toBeVisible();
    const drawer = await page.locator(".investigation-evidence-rail").boundingBox();
    expect(drawer.x).toBeGreaterThan(0);
    expect(drawer.x + drawer.width).toBeLessThanOrEqual(1441);
  });

  test("mobile drawer is a closable bottom sheet and leaves the graph usable", async ({ page }) => {
    await openInvestigation(page, { width: 390, height: 844 });
    const sheet = await page.locator(".investigation-evidence-rail").boundingBox();
    expect(sheet.x).toBeGreaterThanOrEqual(-1);
    expect(sheet.x + sheet.width).toBeLessThanOrEqual(391);
    expect(sheet.y + sheet.height).toBeLessThanOrEqual(845);
    await page.getByRole("button", { name: "Close evidence drawer" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("slider", { name: /Relationship comparison time/ })).toBeVisible();
    await page.getByRole("button", { name: "Inspect supporting evidence" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog")).toBeVisible();
  });
});
