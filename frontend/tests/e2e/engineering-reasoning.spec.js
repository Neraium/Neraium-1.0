import AxeBuilder from "@axe-core/playwright";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, governedComparisonResult, test } from "./fixtures.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const screenshotDirectory = path.resolve(here, "../../../.planning/screenshots/operations-review-investigation");

function reasoningPayload() {
  const analysis = {
    analysis_id: "forensic-analysis",
    generated_at: "2026-07-26T10:00:00Z",
    systems: [{ id: "hydronic", name: "Flow & Pressure" }],
    relationships: [{ id: "chiller-flow", columns: ["Chiller-03", "Flow-01"], change_type: "weakened", baseline_strength: 0.82, current_strength: 0.41, confidence: "qualified" }],
    sii_evidence: {
      source: "sii_result",
      source_path: "sii_result",
      authority: { scope: "canonical_engine_evidence", finding_classification: false },
      status: "complete",
      engine: { name: "SII", version: "4.2" },
      relationship_changes: [{ id: "canonical-flow-pressure", source: "Flow-01", target: "Pressure-01", change_type: "weakened", baseline_correlation: 0.88, current_correlation: 0.46 }],
      operating_context: { status: "comparable", baseline_mode: "mid-load operation", recent_mode: "mid-load operation", match: "strong" },
      persistence: { status: "persistent", method: "elapsed_time_support" },
      uncertainty: { status: "limited", limitations: ["Historian coverage bounds confidence."] },
      data_quality: { status: "degraded", analysis_gate_state: "DEGRADED_READY", warnings: ["Historian X was unavailable during part of the comparison window."] },
      sensor_health: { status: "limited", signals: [{ signal: "Flow-01", health: "suspect" }] },
      configured_prior_observations: [{ observation_id: "prior-1", behavioral_status: "review_required", human_review_required: true }],
      phase_4: { status: "unavailable", available: false, limitations: ["Authenticated workspace identity unavailable."], behavioral_evolution: {}, propagation: {} },
      provenance: { analysis_run_id: "forensic-job", baseline_id: "baseline-42", input_hash: "input-hash" },
    },
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
      finding_confidence_v1: {
        schema_version: "finding-confidence-v1",
        change_detection: { level: "high", reason: "The measured comparison supports a change." },
        interpretation: { level: "medium", attribution_status: "hypothesis", reason: "The system boundary remains the leading hypothesis." },
        persistence: { status: "persistent", reason: "Comparable windows support persistence." },
        operating_context: { level: "high", reason: "Recorded operating context matched." },
        evidence_quality: { level: "high", reason: "Recorded quality checks passed." },
        support_trend: "stable",
        relationship_comparison: { metric: "pearson_correlation", baseline_value: 0.82, current_value: 0.41, signed_change: -0.41, absolute_change: 0.41, direction: "decreased" },
      },
      investigation_guidance: [
        { rank: 1, check: "Verify source data and control-state context.", reason: "Source validation bounds the physical-system interpretation.", category: "data_quality", editable: true },
        { rank: 2, check: "Inspect the affected system boundary.", reason: "The mapped relationship changed at this boundary.", category: "physical_system", editable: true },
        { rank: 3, check: "Confirm the active control state.", reason: "Comparable operation is required.", category: "controls", editable: true },
      ],
      recommended_first_action: "Verify source data and control-state context.",
      activity_timeline: [{ event_type: "baseline_reference", title: "Baseline reference period", start: "2026-07-19T10:00:00Z", end: "2026-07-20T10:00:00Z", precision: "range" }, { event_type: "persistence_supported", title: "Persistence supported", period_label: "Recent comparison window", precision: "period" }, { event_type: "finding_generated", title: "Finding generated", time: "2026-07-26T10:00:00Z", precision: "instant" }],
    }],
  };
  const result = governedComparisonResult({
    job_id: "forensic-job", facility_name: "North Plant", filename: "governed-telemetry.csv", processed_at: "2026-07-26T10:00:00Z",
    sii_reliable_enough_to_show: true, evidence_persisted: true, sii_completed: true, data_quality: { coverage_percent: 82, warnings: ["Historian X was unavailable during the comparison window."] },
    data_gaps: [{ id: "gap-1", source: "Historian X", duration: "1h 55m", signals: ["Flow-01"], overlaps_change_window: true }],
    replay_timeline: { timeline: [{ timestamp: "2026-07-19T10:00:00Z" }, { timestamp: "2026-07-22T10:00:00Z" }] },
    analysis_result: analysis, analysis_explanation: analysis, baseline_analysis: { status: "available", relationship_drift: analysis.relationships },
  });
  const currentUpload = { job_id: result.job_id, filename: result.filename, status: "complete", result };
  return { status: "complete", session_state: "verified", sii_completed: true, latest_result: result, current_upload: currentUpload, snapshot: { status: "complete", sii_completed: true, current_upload: currentUpload, latest_result: result } };
}

async function openSite(page, viewport, payload = reasoningPayload()) {
  const findingCase = {
    finding_id: "evidence-finding-e2e",
    source: { kind: "evidence_run", id: "forensic-job", finding_key: "flow-response" },
    evidence: { finding_key: "flow-response" },
    workflow: {
      version: 3,
      status: "investigating",
      recommended_priority: "high",
      user_priority: null,
      effective_priority: "high",
      assignment: { target_type: "team", label: "Mechanical", external_ref: "TEAM-7" },
      due_at: "2026-08-20T23:59:59Z",
      manager_note: "Verify the system boundary during day shift.",
      work_order_reference: "WO-42",
      external_reference: null,
      validation_outcome: "pending_field_check",
      validation_note: null,
      latest_feedback: null,
      resolution: null,
      updated_at: "2026-08-11T10:00:00Z",
      updated_by: "engineer@example.com",
    },
    activity: { count: 1, latest_event_at: "2026-08-11T10:00:00Z", url: "/api/findings/evidence-finding-e2e/activity" },
  };
  await page.setViewportSize(viewport);
  await page.route("**/api/data/latest-upload**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) }));
  await page.route("**/api/evidence/runs**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ runs: [] }) }));
  await page.route("**/api/facility/context", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
    timezone: "America/Los_Angeles",
    systems: [{ system_id: "hydronic", name: "Flow & Pressure" }],
    equipment: [],
    signal_mappings: [
      { raw_tag: "Chiller-03", normalized_name: "chiller_load", alias: "Chiller load signal", system_id: "hydronic" },
      { raw_tag: "Flow-01", normalized_name: "primary_flow", alias: "Primary chilled-water flow", system_id: "hydronic" },
    ],
  }) }));
  await page.route("**/api/findings**", async (route) => {
    const request = route.request();
    if (request.method() === "PATCH") {
      const changes = request.postDataJSON();
      findingCase.workflow = {
        ...findingCase.workflow,
        version: findingCase.workflow.version + 1,
        status: changes.status ?? findingCase.workflow.status,
        user_priority: changes.user_priority,
        effective_priority: changes.user_priority ?? findingCase.workflow.recommended_priority,
        assignment: changes.assignment,
        due_at: changes.due_at,
        manager_note: changes.manager_note,
        work_order_reference: changes.work_order_reference,
        external_reference: changes.external_reference,
        validation_outcome: changes.validation_outcome,
        validation_note: changes.validation_note,
      };
    }
    const body = request.url().includes("?")
      ? { findings: [findingCase], limit: 100, offset: 0, has_more: false, next_offset: null }
      : findingCase;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/sites/current", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("engineering-reasoning-platform")).toBeVisible();
  await expect(page.getByRole("heading", { name: "1 finding awaiting review" })).toBeVisible();
  await expect(page.locator(".operational-finding")).toBeVisible();
}

test.describe("Daily engineering workflows", () => {
  test.beforeAll(() => mkdirSync(screenshotDirectory, { recursive: true }));

  test("moves from Operations Brief to finding, investigation, evidence, and trace", async ({ page }) => {
    await openSite(page, { width: 1440, height: 900 });
    await expect(page.getByTestId("operations-brief")).toBeVisible();
    await expect(page.getByText("1 finding awaiting review.")).toBeVisible();
    await expect(page.getByText("1 telemetry constraint is being monitored.")).toBeVisible();
    const card = page.locator(".operational-finding");
    await expect(card).toHaveCount(1);
    await expect(card.getByRole("heading", { name: "Pump demand no longer matches flow." })).toBeVisible();
    await expect(card.getByText("Flow & Pressure", { exact: true })).toBeVisible();
    await expect(card.getByText("Equipment / system")).toBeVisible();
    for (const label of ["Finding", "Requested next action", "Why this needs attention", "Evidence and limitations"]) await expect(card.getByText(label, { exact: true })).toBeVisible();
    const workflow = card.locator(".finding-workflow-summary");
    await expect(workflow.getByText("High")).toBeVisible();
    await expect(workflow.getByText("Mechanical")).toBeVisible();
    await expect(workflow.getByText("Investigating")).toHaveCount(0);
    const confidence = card.locator(".finding-confidence-strip");
    await expect(confidence).toContainText("Change confidenceHigh");
    await expect(confidence).not.toContainText("Interpretation");
    await expect(confidence).not.toContainText("Persistence");
    await expect(confidence).not.toContainText("Context");
    await expect(card.getByText("Finding confidence")).toHaveCount(0);
    await expect(card).not.toContainText("Chiller-03");
    await expect(card).not.toContainText("Flow-01");
    await expect(card.getByText("Flow response decreased 12.4%.")).not.toBeVisible();
    await card.getByText("Evidence and limitations").click();
    await expect(card).toContainText("Flow response decreased 12.4%.");
    await expect(card.getByRole("button", { name: "Investigate" })).toBeVisible();
    await expect(card.getByText("Actions")).toBeVisible();
    await page.screenshot({ path: path.join(screenshotDirectory, "finding-desktop.png"), fullPage: true });

    await card.getByRole("button", { name: "Investigate" }).click();
    await expect(page).toHaveURL(/\/findings\/flow-response$/);
    await expect(page.getByRole("heading", { name: "Ownership and next action" })).toBeVisible();
    await expect(page.getByText("Version 3")).toBeVisible();
    for (const heading of ["What changed", "Why this deserves attention", "Important limitations", "What to check first"]) await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await page.screenshot({ path: path.join(screenshotDirectory, "review-desktop.png"), fullPage: true });
    await page.getByRole("button", { name: "Open investigation" }).click();
    await expect(page).toHaveURL(/\/investigations\/flow-response$/);
    await expect(page.getByRole("heading", { name: "Relationships changed" })).toBeVisible();
    await expect(page.getByText("Current review state")).toBeVisible();
    await expect(page.getByText("Jul 26, 2026 · 3:00 AM PDT").first()).toBeVisible();
    await page.screenshot({ path: path.join(screenshotDirectory, "investigation-desktop.png"), fullPage: true });
    await expect(page.getByText("Technical analysis metadata").locator("..")).not.toHaveAttribute("open", "");
    await page.getByText("Technical analysis metadata").click();
    await expect(page.getByText("Chiller-03 / Flow-01").first()).toBeVisible();
    await page.getByRole("button", { name: "Open evidence record" }).click();
    await expect(page).toHaveURL(/\/evidence\/flow-response$/);
    await expect(page.getByRole("heading", { name: "Source lineage" })).toBeVisible();
    await expect(page.getByText("Baseline", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Correlation strength decreased by 0.41 from the learned baseline.")).toBeVisible();
    await expect(page.getByText("Authoritative SII evidence record")).toBeVisible();
    await page.getByText("Authoritative SII evidence record").click();
    await expect(page.getByText("Authenticated workspace identity unavailable.")).toBeVisible();
    await expect(page.getByText("baseline-42")).toBeVisible();
    await expect(page.getByText("Propagation evidence")).toHaveCount(0);
    await page.getByRole("button", { name: "Open trace mode" }).click();
    await expect(page.getByRole("heading", { name: "Trace mode" })).toBeVisible();
  });

  test("mobile keeps the brief item and primary action clear without overflow", async ({ page }) => {
    await openSite(page, { width: 390, height: 844 });
    const card = page.locator(".operational-finding");
    const metrics = await card.evaluate((node) => {
      const header = node.querySelector(".operational-finding__identity")?.getBoundingClientRect();
      const nextAction = node.querySelector(".operational-finding__next")?.getBoundingClientRect();
      const workflow = node.querySelector(".finding-workflow-summary")?.getBoundingClientRect();
      const confidence = node.querySelector(".finding-confidence-strip")?.getBoundingClientRect();
      const action = node.querySelector(".operational-finding__action")?.getBoundingClientRect();
      const cardBox = node.getBoundingClientRect();
      return {
        overflow: document.documentElement.scrollWidth - window.innerWidth,
        cardHeight: cardBox.height,
        headerBeforeWorkflow: Boolean(header && workflow && header.bottom <= workflow.top + 1),
        nextActionBeforeWorkflow: Boolean(nextAction && workflow && nextAction.bottom <= workflow.top + 1),
        workflowBeforeConfidence: Boolean(workflow && confidence && workflow.bottom <= confidence.top + 1),
        confidenceBeforeAction: Boolean(confidence && action && confidence.bottom <= action.top + 1),
        contentFitsCard: [header, nextAction, workflow, confidence, action].every((rect) => rect && rect.left >= cardBox.left - 1 && rect.right <= cardBox.right + 1),
      };
    });
    expect(metrics.overflow).toBeLessThanOrEqual(1);
    expect(metrics.cardHeight).toBeLessThan(650);
    expect(metrics.headerBeforeWorkflow).toBe(true);
    expect(metrics.nextActionBeforeWorkflow).toBe(true);
    expect(metrics.workflowBeforeConfidence).toBe(true);
    expect(metrics.confidenceBeforeAction).toBe(true);
    expect(metrics.contentFitsCard).toBe(true);
    await page.screenshot({ path: path.join(screenshotDirectory, "finding-mobile-390.png"), fullPage: true });
    await card.getByRole("button", { name: "Investigate" }).click();
    await expect(page.getByTestId("finding-review")).toBeVisible();
    await page.screenshot({ path: path.join(screenshotDirectory, "review-mobile-390.png"), fullPage: true });
    await page.getByRole("button", { name: "Open investigation" }).click();
    await expect(page.getByTestId("investigation-workspace")).toBeVisible();
    await page.screenshot({ path: path.join(screenshotDirectory, "investigation-mobile-390.png"), fullPage: true });
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
    await expect(page.locator(".finding-confidence-strip")).toContainText("Change confidence");
  });

  test("back navigation restores Operations Brief context", async ({ page }) => {
    await openSite(page, { width: 390, height: 664 });
    const card = page.locator(".operational-finding").first();
    await expect(card).toBeVisible();
    await card.scrollIntoViewIfNeeded();
    await page.getByRole("button", { name: "Investigate" }).click();
    await expect(page).toHaveURL(/\/findings\/flow-response$/);
    await page.getByRole("button", { name: "Back to Operations Brief" }).click();
    await expect(page).toHaveURL(/\/sites\/current$/);
    await expect(page.getByTestId("operations-brief")).toBeVisible();
    await expect(card).toBeVisible();
    await expect(card.getByRole("button", { name: "Investigate" })).toBeVisible();
  });

  test("asset search opens the evidence record directly", async ({ page }) => {
    await openSite(page, { width: 1280, height: 800 });
    await page.getByRole("combobox", { name: /Search sites/ }).fill("Primary chilled-water flow");
    await page.getByRole("option", { name: "Asset / signal: Primary chilled-water flow" }).click();
    await expect(page).toHaveURL(/\/evidence\/flow-response$/);
    await expect(page.getByTestId("evidence-record")).toBeVisible();
    await expect(page.getByText("Correlation strength decreased by 0.41 from the learned baseline.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Open trace mode" })).toBeVisible();
  });

  test("desktop and mobile workflow surfaces have no serious accessibility violations", async ({ page }) => {
    await openSite(page, { width: 1440, height: 900 });
    for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
      await page.setViewportSize(viewport);
      if (!new URL(page.url()).pathname.startsWith("/sites/")) {
        if (viewport.width < 900) await page.getByRole("button", { name: "Open menu" }).click();
        await page.getByRole("navigation", { name: "Primary navigation" }).getByRole("button", { name: "System Status" }).click();
        await expect(page.getByTestId("operations-brief")).toBeVisible();
      }
      for (const action of [null, "Investigate", "Open investigation"]) {
        if (action) await page.getByRole("button", { name: action }).click();
        const results = await new AxeBuilder({ page }).include("#forensic-main").analyze();
        const serious = results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact));
        expect(serious, serious.map((item) => `${item.id}: ${item.help}`).join("\n")).toEqual([]);
      }
    }
  });
});
