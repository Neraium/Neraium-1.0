import AxeBuilder from "@axe-core/playwright";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, governedComparisonResult, test } from "./fixtures.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const screenshotDirectory = path.resolve(here, "../../../.planning/screenshots/evidence-reference-match-clean");

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
  // Current main requires explicit analysis selection; persisted latest must not activate itself.
  await page.route("**/api/data/analyses/forensic-job", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload.latest_result) }));
  await page.goto("/analyses/forensic-job", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("engineering-reasoning-platform")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Analysis complete" })).toBeVisible();
  await expect(page.locator(".operational-finding")).toBeVisible();
}


test.describe("Results progressive disclosure", () => {
  test.beforeAll(() => {
    mkdirSync(screenshotDirectory, { recursive: true });
  });

  const viewports = [
    { name: "390x844", width: 390, height: 844 },
    { name: "430x932", width: 430, height: 932 },
    { name: "768x1024", width: 768, height: 1024 },
    { name: "1024x768", width: 1024, height: 768 },
    { name: "1366x768", width: 1366, height: 768 },
    { name: "1440x900", width: 1440, height: 900 },
    { name: "1920x1080", width: 1920, height: 1080 },
  ];

  for (const viewport of viewports) {
    test(`${viewport.name} keeps each evidence depth scoped and free of horizontal overflow`, async ({ page }) => {
      await openSite(page, viewport);
      await expect(page.getByText("1 finding deserves review.")).toBeVisible();
      const card = page.getByTestId("compact-finding-card");
      await expect(card).toContainText("Flow & Pressure");
      await expect(card).toContainText("Change confidence");
      await expect(card).not.toContainText("Chiller-03");
      await expect(card).not.toContainText("Flow-01");
      await expect(card.locator("details")).toHaveCount(0);
      await expect(card.getByRole("button")).toHaveCount(1);
      const resultsMetrics = await card.evaluate((node) => ({
        cardHeight: node.getBoundingClientRect().height,
        scrollWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
      }));
      expect(resultsMetrics.cardHeight).toBeLessThanOrEqual(340);
      expect(resultsMetrics.scrollWidth).toBeLessThanOrEqual(resultsMetrics.viewportWidth + 1);
      await card.getByRole("button", { name: "Review finding" }).click();
      for (const heading of ["What changed", "Why this deserves attention", "Evidence assessment", "Important limitation", "Where to investigate next"]) await expect(page.getByRole("heading", { name: heading })).toBeVisible();
      for (const label of ["Change confidence", "Evidence quality", "Persistence", "Operating context", "Corroboration", "Evidence sufficiency"]) await expect(page.locator(".evidence-assessment dt").getByText(label, { exact: true })).toBeVisible();
      await expect(page.getByText("Cause / attribution", { exact: true })).toHaveCount(0);
      await expect(page.getByTestId("finding-review")).not.toContainText("Chiller-03");
      await expect(page.getByTestId("finding-review")).not.toContainText("Flow-01");
      await page.getByRole("button", { name: "Open investigation" }).click();
      for (const heading of ["Primary relationship comparison", "Relationship evidence", "Persistence and confidence", "Operating context", "System evidence channels", "Data quality and comparability", "Timeline", "Source signals and lineage"]) await expect(page.getByRole("heading", { name: heading })).toBeVisible();
      await expect(page.getByText("0.82").first()).toBeVisible();
      await expect(page.getByText("0.41").first()).toBeVisible();
      await expect(page.getByText("Chiller-03").first()).toBeVisible();
      await expect(page.getByText("Analysis-run evidence; not finding-specific").first()).toBeVisible();
      await expect(page.getByRole("heading", { name: "Audit history" })).toHaveCount(0);
      const investigationWidth = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, viewportWidth: innerWidth }));
      expect(investigationWidth.scrollWidth).toBeLessThanOrEqual(investigationWidth.viewportWidth + 1);
      await page.getByRole("button", { name: "Open evidence record" }).click();
      const dashboard = page.locator(".evidence-dashboard");
      await expect(dashboard).toBeVisible();
      await expect(dashboard.getByText("Finding", { exact: true })).toBeVisible();
      await expect(dashboard.getByRole("heading", { level: 1 })).toBeVisible();
      await expect(dashboard.getByLabel("Finding context")).toBeVisible();
      await expect(dashboard.getByLabel("Evidence metrics")).toBeVisible();
      await expect(dashboard.getByRole("heading", { name: "Strongest Relationship Changes" })).toBeVisible();
      await expect(dashboard.getByText("Cause established?", { exact: true })).toHaveCount(0);
      await expect(dashboard).not.toContainText(/likely cause|probable cause|root cause|suspected cause|diagnosis/i);
      await expect(dashboard.getByText("No — investigation required", { exact: true })).toHaveCount(0);
      await page.screenshot({ path: path.join(screenshotDirectory, `${viewport.name}.png`) });
      const technicalEvidence = page.getByText("Technical evidence and audit trail", { exact: true });
      await expect(technicalEvidence).toBeVisible();
      await technicalEvidence.click();
      for (const heading of ["Record identity", "Finding-owned relationships", "Finding provenance and lineage", "Evidence sufficiency", "Audit history"]) await expect(page.getByRole("heading", { name: heading }).first()).toBeVisible();
      await expect(page.getByTestId("evidence-record")).toContainText("pearson_correlation");
      await expect(page.getByTestId("evidence-record")).toContainText("Chiller-03");
      await expect(page.getByTestId("evidence-record")).toContainText("Authenticated workspace identity unavailable.");
      await expect(page.getByTestId("evidence-record")).toContainText("Analysis-run evidence; not finding-specific");
      const evidenceWidth = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, viewportWidth: innerWidth }));
      expect(evidenceWidth.scrollWidth).toBeLessThanOrEqual(evidenceWidth.viewportWidth + 1);
    });
  }

  test("unknown detail identities fail closed at every depth", async ({ page }) => {
    await openSite(page, { width: 390, height: 844 });
    for (const [route, heading] of [["findings", "Finding unavailable"], ["investigations", "Investigation unavailable"], ["evidence", "Evidence record unavailable"]]) {
      await page.goto(`/${route}/workspace-b-secret`);
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
      await expect(page.locator("body")).not.toContainText("workspace-b-secret");
      await expect(page.locator("body")).not.toContainText("Flow response changed");
    }
  });

  test("primary hierarchy has no serious accessibility violations", async ({ page }) => {
    await openSite(page, { width: 390, height: 844 });
    for (const action of [null, "Review finding", "Open investigation", "Open evidence record"]) {
      if (action) await page.getByRole("button", { name: action }).click();
      const results = await new AxeBuilder({ page }).include("#forensic-main").analyze();
      const serious = results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact));
      expect(serious, serious.map((item) => `${item.id}: ${item.help}`).join("\n")).toEqual([]);
    }
  });
});
