import AxeBuilder from "@axe-core/playwright";
import { expect, governedComparisonResult, test } from "./fixtures.js";

function reasoningPayload() {
  const analysis = {
    analysis_id: "forensic-analysis",
    generated_at: "2026-07-26T10:00:00Z",
    systems: [{ id: "hydronic", name: "Flow & Pressure" }],
    relationships: [{ id: "chiller-flow", columns: ["Chiller-03", "Flow-01"], change_type: "weakened", baseline_strength: 0.82, current_strength: 0.41, confidence: "qualified" }],
    insights: [{
      id: "flow-response", title: "Flow response changed", confidence: "high", system: "Flow & Pressure",
      what_changed: "Flow response weakened under comparable demand.",
      why_it_matters: "The mapped subsystem response differs from the learned comparison.",
      variables: ["Chiller-03", "Flow-01"],
      supporting_evidence: ["Flow response decreased 12.4%.", "Pump demand increased 6.1%.", "The relationship moved outside its learned range."],
      contributing_relationships: [{ id: "chiller-flow", columns: ["Chiller-03", "Flow-01"], change_type: "weakened", baseline_strength: 0.82, current_strength: 0.41 }],
      classification: { type: "unexplained_systemic_change", label: "Unexplained systemic change", confidence: "high", reasons: ["Operating context matched strongly.", "The relationship shift remained persistent."], alternative_explanations: ["An undocumented control-state change may still explain the shift."], certainty_limit: "This describes a relationship change and does not establish a cause." },
      data_confidence: { rating: "high", summary: "Telemetry passed recorded quality checks.", reasons: [] },
      operating_mode: { match: "strong", confidence: "high", baseline_mode_label: "Mid-load operation", recent_mode_label: "Mid-load operation", differences: [] },
      sensor_health: [{ signal: "Flow-01", health: "healthy", conditions: [] }],
      persistence: { persistent: true, duration: "3 days", summary: "The relationship shift remained present across comparable windows." },
      investigation_guidance: [
        { rank: 1, check: "Verify source data and control-state context.", reason: "Source validation bounds the physical-system interpretation.", category: "data_quality", editable: true },
        { rank: 2, check: "Inspect the affected system boundary.", reason: "The mapped relationship changed at this boundary.", category: "physical_system", editable: true },
        { rank: 3, check: "Confirm the active control state.", reason: "Comparable operation is required.", category: "controls", editable: true },
      ],
      activity_timeline: [{ event_type: "baseline_reference", title: "Baseline reference period", start: "2026-07-19T10:00:00Z", end: "2026-07-20T10:00:00Z", precision: "range" }, { event_type: "persistence_supported", title: "Persistence supported", period_label: "Recent comparison window", precision: "period" }],
    }],
  };
  const result = governedComparisonResult({
    job_id: "forensic-job", facility_name: "North Plant", filename: "governed-telemetry.csv", processed_at: "2026-07-26T10:00:00Z",
    sii_reliable_enough_to_show: true, sii_completed: true, data_quality: { coverage_percent: 82, warnings: ["Historian X was unavailable during the comparison window."] },
    data_gaps: [{ id: "gap-1", source: "Historian X", duration: "1h 55m", signals: ["Flow-01"], overlaps_change_window: true }],
    replay_timeline: { timeline: [{ timestamp: "2026-07-19T10:00:00Z" }, { timestamp: "2026-07-22T10:00:00Z" }] },
    analysis_result: analysis, analysis_explanation: analysis, baseline_analysis: { status: "available", relationship_drift: analysis.relationships },
  });
  const currentUpload = { job_id: result.job_id, filename: result.filename, status: "complete", result };
  return { status: "complete", session_state: "verified", sii_completed: true, latest_result: result, current_upload: currentUpload, snapshot: { status: "complete", sii_completed: true, current_upload: currentUpload, latest_result: result } };
}

async function openSite(page, viewport, payload = reasoningPayload()) {
  await page.setViewportSize(viewport);
  await page.route("**/api/data/latest-upload**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) }));
  await page.route("**/api/evidence/runs**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ runs: [] }) }));
  await page.goto("/sites/current", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("engineering-reasoning-platform")).toBeVisible();
  await expect(page.getByRole("heading", { name: "North Plant" })).toBeVisible();
  await expect(page.locator(".operational-finding")).toBeVisible();
}

test.describe("Daily engineering workflows", () => {
  test("moves from Operations Brief to finding, investigation, evidence, and trace", async ({ page }) => {
    await openSite(page, { width: 1440, height: 900 });
    await expect(page.getByTestId("operations-brief")).toBeVisible();
    await expect(page.getByText("No new unexplained changes.")).toBeVisible();
    const card = page.locator(".operational-finding");
    await expect(card).toHaveCount(1);
    await expect(card.getByRole("heading", { name: "Pump demand no longer matches flow" })).toBeVisible();
    await expect(card.getByText("Flow & Pressure")).toBeVisible();
    await expect(card.getByText("Confidence")).toBeVisible();
    await expect(card.getByText("Narrowed")).toBeVisible();
    const evidence = card.locator(".operational-finding__evidence");
    await expect(evidence).not.toHaveAttribute("open", "");
    await expect(evidence.getByText("Flow response decreased 12.4%.")).toBeHidden();
    await evidence.locator("summary").click();
    await expect(evidence.getByText("Flow response decreased 12.4%.")).toBeVisible();
    await expect(evidence.getByText("Pump demand increased 6.1%.")).toBeVisible();
    await expect(card.getByRole("button", { name: "Review" })).toBeVisible();
    await expect(card.getByText("More actions")).toBeVisible();

    await card.getByRole("button", { name: "Review" }).click();
    await expect(page).toHaveURL(/\/findings\/flow-response$/);
    await expect(page.getByText("What changed")).toBeVisible();
    await expect(page.getByText("What to check first")).toBeVisible();
    await page.getByRole("button", { name: "Open investigation" }).click();
    await expect(page).toHaveURL(/\/investigations\/flow-response$/);
    await expect(page.getByText("Investigation guidance")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Current review state" })).toBeVisible();
    await expect(page.getByText("Technical analysis metadata").locator("..")).not.toHaveAttribute("open", "");
    await page.getByRole("button", { name: "Open evidence record" }).click();
    await expect(page).toHaveURL(/\/evidence\/flow-response$/);
    await expect(page.getByRole("heading", { name: "Source lineage" })).toBeVisible();
    await expect(page.getByText("Baseline relationship value")).toBeVisible();
    await page.getByRole("button", { name: "Open trace mode" }).click();
    await expect(page.getByRole("heading", { name: "Trace mode" })).toBeVisible();
  });

  test("mobile keeps the brief item and primary action clear without overflow", async ({ page }) => {
    await openSite(page, { width: 390, height: 844 });
    const card = page.locator(".operational-finding");
    const metrics = await card.evaluate((node) => {
      const header = node.querySelector(".operational-finding__alert")?.getBoundingClientRect();
      const evidence = node.querySelector(".operational-finding__evidence")?.getBoundingClientRect();
      const action = node.querySelector(".operational-finding__action")?.getBoundingClientRect();
      const cardBox = node.getBoundingClientRect();
      return {
        overflow: document.documentElement.scrollWidth - window.innerWidth,
        headerBeforeEvidence: Boolean(header && evidence && header.bottom <= evidence.top + 1),
        evidenceBeforeAction: Boolean(evidence && action && evidence.bottom <= action.top + 1),
        actionVisible: Boolean(action && action.top < window.innerHeight),
        contentFitsCard: [header, evidence, action].every((rect) => rect && rect.left >= cardBox.left - 1 && rect.right <= cardBox.right + 1),
      };
    });
    expect(metrics.overflow).toBeLessThanOrEqual(1);
    expect(metrics.headerBeforeEvidence).toBe(true);
    expect(metrics.evidenceBeforeAction).toBe(true);
    expect(metrics.actionVisible).toBe(true);
    expect(metrics.contentFitsCard).toBe(true);
  });

  test("long system and signal names reflow at narrow Safari-like viewport heights", async ({ page }) => {
    const payload = reasoningPayload();
    const result = payload.latest_result;
    const analysis = result.analysis_explanation;
    const longSystem = "North Campus Condenser Water Distribution and Pressure Boundary";
    const longSignal = "Extremely long condenser discharge pressure transmitter identifier";
    analysis.systems[0].name = longSystem;
    analysis.insights[0].system = longSystem;
    analysis.insights[0].variables = [longSignal, "Compressor demand signal with extended historian naming"];
    analysis.insights[0].contributing_relationships[0].columns = analysis.insights[0].variables;
    analysis.relationships[0].columns = analysis.insights[0].variables;
    await openSite(page, { width: 320, height: 664 }, payload);
    const metrics = await page.evaluate(() => ({ root: document.documentElement.scrollWidth, body: document.body.scrollWidth, viewport: innerWidth }));
    expect(metrics.root).toBeLessThanOrEqual(metrics.viewport + 1);
    expect(metrics.body).toBeLessThanOrEqual(metrics.viewport + 1);
    await expect(page.getByText(longSystem).first()).toBeVisible();
    await expect(page.locator(".operational-finding__evidence summary")).toBeVisible();
  });

  test("back navigation restores Operations Brief context", async ({ page }) => {
    await openSite(page, { width: 390, height: 664 });
    await page.locator(".operational-finding").scrollIntoViewIfNeeded();
    const priorScroll = await page.evaluate(() => window.scrollY);
    expect(priorScroll).toBeGreaterThan(0);
    await page.getByRole("button", { name: "Review" }).click();
    await expect(page).toHaveURL(/\/findings\/flow-response$/);
    await page.getByRole("button", { name: "Back to Operations Brief" }).click();
    await expect(page).toHaveURL(/\/sites\/current$/);
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(priorScroll);
  });

  test("asset search opens the evidence record directly", async ({ page }) => {
    await openSite(page, { width: 1280, height: 800 });
    await page.getByRole("combobox", { name: /Search sites/ }).fill("Chiller-03");
    await page.getByRole("option", { name: "Asset / signal: Chiller-03" }).click();
    await expect(page).toHaveURL(/\/evidence\/flow-response$/);
    await expect(page.getByTestId("evidence-record")).toBeVisible();
    await expect(page.getByRole("button", { name: "Open trace mode" })).toBeVisible();
  });

  test("desktop and mobile workflow surfaces have no serious accessibility violations", async ({ page }) => {
    for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
      await openSite(page, viewport);
      for (const action of [null, "Review", "Open investigation"]) {
        if (action) await page.getByRole("button", { name: action }).click();
        const results = await new AxeBuilder({ page }).include("#forensic-main").analyze();
        const serious = results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact));
        expect(serious, serious.map((item) => `${item.id}: ${item.help}`).join("\n")).toEqual([]);
      }
    }
  });
});
