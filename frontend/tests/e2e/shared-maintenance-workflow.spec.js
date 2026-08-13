import AxeBuilder from "@axe-core/playwright";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, governedComparisonResult, test } from "./fixtures.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const screenshotDirectory = path.resolve(here, "../../../.planning/screenshots/shared-maintenance-workflow");

function analyticalPayload() {
  const analysis = {
    analysis_id: "maintenance-workflow-analysis",
    generated_at: "2026-08-12T08:00:00Z",
    systems: [{ id: "chw-loop", name: "North Plant · Chilled Water Loop" }],
    relationships: [{ id: "pump-flow", columns: ["CHWP-2-SPD", "CHWP-2-FLOW"], change_type: "weakened", baseline_strength: 0.84, current_strength: 0.46, confidence: "qualified" }],
    insights: [{
      id: "pump-response",
      title: "Pump discharge response changed",
      headline: "Pump discharge response is slower under comparable demand",
      confidence: "high",
      system: "North Plant · Chilled Water Loop",
      system_name: "North Plant · Chilled Water Loop",
      equipment_name: "CHWP-2 · Mechanical Room 2",
      what_changed: "Pump discharge response is slower under comparable demand.",
      why_it_matters: "The chilled-water loop is responding differently from its established behavior.",
      variables: ["CHWP-2-SPD", "CHWP-2-FLOW"],
      next_checks: ["Inspect CHWP-2 for vibration, belt condition, leaks, and unusual noise."],
      recommended_investigation: [{ rank: 1, check: "Inspect CHWP-2 for vibration, belt condition, leaks, and unusual noise.", reason: "A field inspection can confirm whether the behavioral change has a physical correlate." }],
      supporting_evidence: ["The response change persisted across comparable operating windows.", "Recorded demand remained within the established operating range."],
      contributing_relationships: [{ id: "pump-flow", columns: ["CHWP-2-SPD", "CHWP-2-FLOW"], change_type: "weakened", baseline_strength: 0.84, current_strength: 0.46 }],
      classification: { type: "unexplained_systemic_change", label: "Persistent operating change", confidence: "high", reasons: ["Comparable operating context supported the comparison."], alternative_explanations: ["An undocumented operating change may still explain the observation."], certainty_limit: "The evidence identifies a behavioral change, not its cause." },
      data_confidence: { rating: "high", summary: "Recorded quality checks passed.", reasons: [] },
      operating_mode: { match: "strong", confidence: "high", baseline_mode_label: "Daytime mid-load", recent_mode_label: "Daytime mid-load", differences: [] },
      sensor_health: [{ signal: "CHWP-2-FLOW", health: "healthy", conditions: [] }],
      persistence: { persistent: true, duration: "4 days", summary: "The response change remained present across comparable windows." },
      finding_confidence_v1: {
        schema_version: "finding-confidence-v1",
        change_detection: { level: "high", reason: "The measured comparison supports a change." },
        interpretation: { level: "medium", attribution_status: "hypothesis", reason: "A field inspection is still required." },
        persistence: { status: "persistent", reason: "Comparable windows support persistence." },
        operating_context: { level: "high", reason: "Recorded context matched." },
        evidence_quality: { level: "high", reason: "Recorded quality checks passed." },
        support_trend: "stable",
        relationship_comparison: { metric: "pearson_correlation", baseline_value: 0.84, current_value: 0.46, signed_change: -0.38, absolute_change: 0.38, direction: "decreased" },
      },
      investigation_guidance: [
        { rank: 1, check: "Inspect CHWP-2 at Mechanical Room 2.", reason: "Confirm whether a physical condition accompanies the recorded change.", category: "physical_system", editable: true },
        { rank: 2, check: "Compare the local gauge with the recorded flow signal.", reason: "This bounds the interpretation of the recorded behavior.", category: "data_quality", editable: true },
      ],
      activity_timeline: [{ event_type: "baseline_reference", title: "Baseline reference period", start: "2026-08-01T08:00:00Z", end: "2026-08-02T08:00:00Z", precision: "range" }],
    }],
  };
  const result = governedComparisonResult({
    job_id: "maintenance-workflow-run",
    facility_name: "North Plant",
    filename: "north-plant-comparison.csv",
    processed_at: "2026-08-12T08:00:00Z",
    sii_reliable_enough_to_show: true,
    sii_completed: true,
    data_quality: { coverage_percent: 96, warnings: [] },
    replay_timeline: { timeline: [{ timestamp: "2026-08-01T08:00:00Z" }, { timestamp: "2026-08-12T08:00:00Z" }] },
    analysis_result: analysis,
    analysis_explanation: analysis,
    baseline_analysis: { status: "available", relationship_drift: analysis.relationships },
  });
  const currentUpload = { job_id: result.job_id, filename: result.filename, status: "complete", result };
  return { status: "complete", session_state: "verified", sii_completed: true, latest_result: result, current_upload: currentUpload, snapshot: { status: "complete", sii_completed: true, current_upload: currentUpload, latest_result: result } };
}

function workflow(overrides = {}) {
  return {
    version: 1,
    status: "open",
    recommended_priority: "high",
    user_priority: null,
    effective_priority: "high",
    assignment: null,
    assigned_by: "E2E Morgan Lead",
    due_at: "2026-08-14T23:59:59Z",
    manager_note: "Begin with a visual and audible inspection while the pump is running.",
    latest_field_report: null,
    field_reports: [],
    resolution: null,
    updated_at: "2026-08-12T09:00:00Z",
    updated_by: "lead.e2e@neraium.test",
    ...overrides,
  };
}

function finding(id, workflowOverrides = {}, analyticalOverrides = {}) {
  return {
    finding_id: id,
    source: { kind: "evidence_run", id: "maintenance-workflow-run", run_id: "maintenance-workflow-run", finding_key: "pump-response" },
    evidence: {
      source_run_id: "maintenance-workflow-run",
      source_finding_key: "pump-response",
      recommended_priority: "high",
      finding: {
        headline: "Pump discharge response is slower under comparable demand",
        system_name: "North Plant · Chilled Water Loop",
        equipment_name: "CHWP-2 · Mechanical Room 2",
        what_changed: "Pump discharge response is slower under comparable demand.",
        why_it_matters: "The chilled-water loop is responding differently from its established behavior.",
        next_checks: ["Inspect CHWP-2 for vibration, belt condition, leaks, and unusual noise."],
        confidence: "high",
        ...analyticalOverrides,
      },
    },
    workflow: workflow(workflowOverrides),
    activity: { count: 3, latest_event_at: "2026-08-12T10:00:00Z", url: `/api/findings/${id}/activity` },
    created_at: "2026-08-12T08:00:00Z",
  };
}

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function installWorkflowApi(page, { role = "operator", technicianStatus = "open" } = {}) {
  const user = role === "viewer"
    ? { email: "taylor.tech.e2e@neraium.test", name: "E2E Taylor Technician", role: "viewer" }
    : { email: "lead.e2e@neraium.test", name: "E2E Morgan Lead", role };
  const members = [
    { member_id: "taylor.tech.e2e@neraium.test", display_name: "E2E Taylor Technician", role: "viewer", is_active: true },
    { member_id: "riley.tech.e2e@neraium.test", display_name: "E2E Riley Technician", role: "viewer", is_active: true },
    { member_id: "lead.e2e@neraium.test", display_name: "E2E Morgan Lead", role: "operator", is_active: true },
  ];
  const cases = new Map([
    ["finding-unassigned", finding("finding-unassigned")],
    ["finding-mine", finding("finding-mine", { assignment: { target_type: "person", label: "E2E Morgan Lead", external_ref: "lead.e2e@neraium.test" }, status: "investigating" }, { equipment_name: "CHWP-1 · Mechanical Room 1", headline: "Pump response remains changed during mid-load operation" })],
    ["finding-review", finding("finding-review", {
      version: 4,
      status: "awaiting_review",
      assignment: { target_type: "person", label: "E2E Taylor Technician", external_ref: "taylor.tech.e2e@neraium.test" },
      latest_field_report: { inspected: "Pump coupling guard, bearings, seals, and local gauge", found: "Light bearing vibration; no leak or abnormal heat", action_taken: "Tightened the loose guard fastener", problem_found: "yes", needs_escalation: false, investigation_complete: true, note: "Recommend reviewing vibration at the next operating round.", actor: "E2E Taylor Technician", recorded_at: "2026-08-12T10:00:00Z" },
    })],
    ["finding-technician", finding("finding-technician", {
      status: technicianStatus,
      assignment: { target_type: "person", label: "E2E Taylor Technician", external_ref: "taylor.tech.e2e@neraium.test" },
    })],
  ]);
  const mutationBodies = [];
  const activity = new Map([...cases.keys()].map((id) => [id, [
    { label: "Finding detected", summary: "Neraium surfaced a persistent operating change.", actor: "Neraium", recorded_at: "2026-08-12T08:00:00Z", version: 0 },
    { label: "Finding assigned", summary: `Assigned to ${cases.get(id).workflow.assignment?.label || "the maintenance queue"}.`, actor: "E2E Morgan Lead", recorded_at: "2026-08-12T09:00:00Z", version: 1 },
  ]]));

  await page.route("**/api/auth/me", (route) => json(route, { authenticated: true, user }));
  await page.route("**/api/data/latest-upload**", (route) => json(route, analyticalPayload()));
  await page.route("**/api/evidence/runs**", (route) => json(route, { runs: [] }));
  await page.route("**/api/facility/context", (route) => json(route, {
    systems: [{ system_id: "chw-loop", name: "North Plant · Chilled Water Loop" }],
    equipment: [{ id: "chwp-2", name: "CHWP-2", system_id: "chw-loop", location: "Mechanical Room 2" }],
    signal_mappings: [
      { raw_tag: "CHWP-2-SPD", normalized_name: "pump_speed", alias: "CHWP-2 speed", system_id: "chw-loop" },
      { raw_tag: "CHWP-2-FLOW", normalized_name: "pump_flow", alias: "CHWP-2 discharge flow", system_id: "chw-loop" },
    ],
  }));
  await page.route("**/api/findings**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const parts = url.pathname.split("/").filter(Boolean);
    const id = parts[2] || "";
    const endpoint = parts[3] || "";
    if (url.pathname === "/api/findings/members") return json(route, { members });
    if (id && endpoint === "activity") return json(route, { activity: activity.get(id) || [] });
    if (id && endpoint === "workflow" && request.method() === "PATCH") {
      const body = request.postDataJSON();
      mutationBodies.push({ id, endpoint, body });
      const item = cases.get(id);
      item.workflow = {
        ...item.workflow,
        version: item.workflow.version + 1,
        status: body.status ?? item.workflow.status,
        user_priority: Object.hasOwn(body, "user_priority") ? body.user_priority : item.workflow.user_priority,
        effective_priority: Object.hasOwn(body, "user_priority") ? body.user_priority ?? item.workflow.recommended_priority : item.workflow.effective_priority,
        assignment: Object.hasOwn(body, "assignment") ? body.assignment : item.workflow.assignment,
        assigned_by: "E2E Morgan Lead",
        due_at: Object.hasOwn(body, "due_at") ? body.due_at : item.workflow.due_at,
        manager_note: Object.hasOwn(body, "manager_note") ? body.manager_note : item.workflow.manager_note,
      };
      activity.get(id).push({ label: body.assignment ? "Finding reassigned" : "Work status changed", summary: body.assignment ? `Assigned to ${body.assignment.label}.` : `Status changed to ${body.status}.`, actor: user.name, recorded_at: "2026-08-12T11:00:00Z", version: item.workflow.version });
      return json(route, item);
    }
    if (id && endpoint === "field-reports" && request.method() === "POST") {
      const body = request.postDataJSON();
      mutationBodies.push({ id, endpoint, body });
      const item = cases.get(id);
      const report = { ...body, actor: user.name, recorded_at: "2026-08-12T11:30:00Z" };
      item.workflow = { ...item.workflow, version: item.workflow.version + 1, status: body.needs_escalation ? "escalated" : body.investigation_complete ? "awaiting_review" : item.workflow.status, latest_field_report: report, field_reports: [...item.workflow.field_reports, report] };
      activity.get(id).push({ label: body.needs_escalation ? "Escalation requested" : "Field report added", summary: `${user.name} recorded the field investigation.`, actor: user.name, recorded_at: report.recorded_at, version: item.workflow.version });
      return json(route, item);
    }
    if (id && endpoint === "resolution" && request.method() === "POST") {
      const body = request.postDataJSON();
      mutationBodies.push({ id, endpoint, body });
      const item = cases.get(id);
      item.workflow = { ...item.workflow, version: item.workflow.version + 1, status: "resolved", resolution: { outcome: body.outcome, note: body.note, resolved_at: "2026-08-12T12:00:00Z" } };
      activity.get(id).push({ label: "Finding resolved", summary: "The lead reviewed and resolved the finding.", actor: user.name, recorded_at: "2026-08-12T12:00:00Z", version: item.workflow.version });
      return json(route, item);
    }
    if (id && !endpoint) return json(route, cases.get(id) || {}, cases.has(id) ? 200 : 404);
    let items = [...cases.values()];
    if (url.searchParams.get("assigned_to_me") === "true") items = items.filter((item) => item.workflow.assignment?.external_ref === user.email);
    if (url.searchParams.get("unassigned") === "true") items = items.filter((item) => !item.workflow.assignment);
    if (url.searchParams.get("active") === "true") items = items.filter((item) => !["resolved", "dismissed"].includes(item.workflow.status));
    if (url.searchParams.get("in_progress") === "true") items = items.filter((item) => ["acknowledged", "investigating", "waiting", "escalated"].includes(item.workflow.status));
    if (url.searchParams.get("awaiting_review") === "true") items = items.filter((item) => item.workflow.status === "awaiting_review");
    if (url.searchParams.get("recently_resolved") === "true") items = items.filter((item) => ["resolved", "dismissed"].includes(item.workflow.status));
    if (url.searchParams.get("status")) items = items.filter((item) => item.workflow.status === url.searchParams.get("status"));
    if (url.searchParams.get("priority")) items = items.filter((item) => item.workflow.effective_priority === url.searchParams.get("priority"));
    if (url.searchParams.get("assignee")) items = items.filter((item) => item.workflow.assignment?.external_ref === url.searchParams.get("assignee"));
    if (url.searchParams.get("system")) items = items.filter((item) => item.evidence.finding.system_name.toLowerCase().includes(url.searchParams.get("system").toLowerCase()));
    return json(route, { findings: items, limit: 30, offset: 0, has_more: false, next_offset: null });
  });
  return { cases, mutationBodies, user };
}

function captureBrowserErrors(page) {
  const errors = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  return errors;
}

async function expectNoSeriousAccessibilityIssues(page) {
  const results = await new AxeBuilder({ page })
    .include("#forensic-main")
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  const serious = results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact));
  expect(serious, serious.map((violation) => `${violation.id}: ${violation.help}`).join("\n")).toEqual([]);
}

async function expectNoHorizontalOverflow(page) {
  const widths = await page.evaluate(() => ({ viewport: innerWidth, root: document.documentElement.scrollWidth, body: document.body.scrollWidth }));
  expect(widths.root).toBeLessThanOrEqual(widths.viewport + 1);
  expect(widths.body).toBeLessThanOrEqual(widths.viewport + 1);
}

test.describe("Shared maintenance workflow", () => {
  test.beforeAll(() => mkdirSync(screenshotDirectory, { recursive: true }));

  test("lead scans team queues, delegates real members, and reviews outcomes", async ({ page }) => {
    const errors = captureBrowserErrors(page);
    const state = await installWorkflowApi(page, { role: "operator" });
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.goto("/work", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("work-queue-workspace")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Work", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "My Work" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "Needs assignment" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "CHWP-1 · Mechanical Room 1" })).toBeVisible();

    await page.getByRole("button", { name: "Team Findings" }).click();
    await expect(page.getByRole("button", { name: "More filters" })).toBeVisible();
    await expect(page.locator("#work-queue-controls")).toBeHidden();
    await page.getByRole("button", { name: "Needs assignment" }).click();
    const unassignedCard = page.getByTestId("work-finding-card");
    await expect(unassignedCard).toHaveCount(1);
    await expect(unassignedCard.getByText("Unassigned")).toBeVisible();
    await unassignedCard.getByRole("button", { name: /Open CHWP-2/ }).click();

    const leadControls = page.locator(".lead-controls");
    await expect(page.getByRole("button", { name: "Accept work" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Report what you found" })).toHaveCount(0);
    await leadControls.getByLabel("Assign to").selectOption("taylor.tech.e2e@neraium.test");
    await leadControls.getByLabel("Priority").selectOption("critical");
    await leadControls.getByLabel("Due date").fill("2026-08-13");
    await leadControls.getByLabel("Guidance for the technician").fill("Inspect the coupling guard and bearings first; call the lead if vibration is severe.");
    await leadControls.getByRole("button", { name: "Save work details" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Assignment and guidance saved." })).toBeVisible();
    expect(state.mutationBodies.at(-1).body).toMatchObject({
      assignment: { target_type: "person", label: "E2E Taylor Technician", external_ref: "taylor.tech.e2e@neraium.test" },
      user_priority: "critical",
      due_at: "2026-08-13T23:59:59Z",
      manager_note: "Inspect the coupling guard and bearings first; call the lead if vibration is severe.",
    });

    await leadControls.getByLabel("Assign to").selectOption("riley.tech.e2e@neraium.test");
    await leadControls.getByRole("button", { name: "Save work details" }).click();
    await expect.poll(() => state.mutationBodies.filter((item) => item.endpoint === "workflow").length).toBe(2);
    expect(state.mutationBodies.at(-1).body.assignment).toEqual({ target_type: "person", label: "E2E Riley Technician", external_ref: "riley.tech.e2e@neraium.test" });

    await page.getByRole("button", { name: "Back to work list" }).click();
    await page.getByRole("button", { name: "Awaiting review" }).click();
    await page.getByRole("button", { name: /Open CHWP-2/ }).click();
    await expect(page.getByRole("heading", { name: "Latest field report" })).toBeVisible();
    await expect(page.getByText("Light bearing vibration; no leak or abnormal heat")).toBeVisible();
    await expect(page.getByText("Finding detected")).toBeVisible();
    await page.screenshot({ path: path.join(screenshotDirectory, "lead-desktop.png"), fullPage: true });

    await leadControls.getByRole("button", { name: "Return for investigation" }).click();
    await expect(page.locator(".work-brief__urgency").getByText("In progress", { exact: true })).toBeVisible();
    await leadControls.getByRole("button", { name: "Monitor", exact: true }).click();
    await expect(page.locator(".work-brief__urgency").getByText("Monitoring", { exact: true })).toBeVisible();
    await leadControls.getByRole("button", { name: "Resolve", exact: true }).click();
    await expect(page.locator(".work-brief__urgency").getByText("Resolved", { exact: true })).toBeVisible();
    expect(state.mutationBodies.map((item) => item.endpoint)).toContain("resolution");

    await expectNoSeriousAccessibilityIssues(page);
    await expectNoHorizontalOverflow(page);
    expect(errors).toEqual([]);
  });

  test("390px technician accepts, starts, reports, and escalates field work", async ({ page }) => {
    const errors = captureBrowserErrors(page);
    const state = await installWorkflowApi(page, { role: "viewer" });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/work/finding-technician", { waitUntil: "domcontentloaded" });
    const brief = page.locator(".work-brief");
    await expect(brief).toBeVisible();
    await expect(brief.getByRole("heading", { name: "CHWP-2 · Mechanical Room 2" })).toBeVisible();
    await expect(brief.getByText("North Plant · Chilled Water Loop")).toBeVisible();
    await expect(brief.getByText("Pump discharge response is slower under comparable demand", { exact: true })).toBeVisible();
    await expect(brief.getByText("E2E Morgan Lead", { exact: true })).toBeVisible();
    await expect(brief.getByText(/Due/).first()).toBeVisible();
    await expect(brief.getByText("Inspect CHWP-2 for vibration, belt condition, leaks, and unusual noise.")).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await expectNoSeriousAccessibilityIssues(page);
    await page.screenshot({ path: path.join(screenshotDirectory, "technician-390.png"), fullPage: true });

    const accept = brief.getByRole("button", { name: "Accept work" });
    expect(await accept.evaluate((node) => node.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    await accept.click();
    const start = brief.getByRole("button", { name: "Start investigation" });
    await expect(start).toBeVisible();
    expect(await start.evaluate((node) => node.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    await start.click();

    await brief.getByLabel("What did you inspect?").fill("Coupling guard, bearings, seals, and local discharge gauge");
    await brief.getByLabel("What did you find?").fill("Pronounced bearing vibration; no visible leak");
    await brief.getByLabel("Action taken, if any").fill("Secured the loose coupling guard fastener");
    await brief.getByLabel("Yes", { exact: true }).check();
    await brief.getByLabel("Additional note").fill("Vibration remains after securing the guard.");
    await brief.getByLabel("I need help or engineering escalation").check();
    await brief.getByLabel("My investigation is complete").check();
    const submit = brief.getByRole("button", { name: "Send for review" });
    expect(await submit.evaluate((node) => node.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    await submit.click();
    await expect(page.locator(".work-brief__urgency").getByText("Escalated", { exact: true })).toBeVisible();
    await expect(page.getByText("Pronounced bearing vibration; no visible leak")).toBeVisible();
    const report = state.mutationBodies.find((item) => item.endpoint === "field-reports")?.body;
    expect(report).toMatchObject({
      inspected: "Coupling guard, bearings, seals, and local discharge gauge",
      found: "Pronounced bearing vibration; no visible leak",
      action_taken: "Secured the loose coupling guard fastener",
      problem_found: "yes",
      needs_escalation: true,
      investigation_complete: true,
    });
    await expectNoHorizontalOverflow(page);
    expect(errors).toEqual([]);
  });

  test("engineer reaches investigation and technical evidence from the same work item", async ({ page }) => {
    const errors = captureBrowserErrors(page);
    await installWorkflowApi(page, { role: "operator" });
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.goto("/work/finding-review", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "Open investigation" }).click();
    await expect(page).toHaveURL(/\/investigations\/pump-response$/);
    await expect(page.getByText("Investigation guidance")).toBeVisible();
    await page.getByRole("button", { name: "Open evidence record" }).click();
    await expect(page).toHaveURL(/\/evidence\/pump-response$/);
    await expect(page.getByRole("heading", { name: "Source lineage" })).toBeVisible();
    await expect(page.getByText("Baseline", { exact: true })).toBeVisible();
    await expect(page.getByText("CHWP-2-SPD / CHWP-2-FLOW")).toBeVisible();
    await page.screenshot({ path: path.join(screenshotDirectory, "engineer-evidence-desktop.png"), fullPage: true });
    await expectNoSeriousAccessibilityIssues(page);
    await expectNoHorizontalOverflow(page);
    expect(errors).toEqual([]);
  });

  test("maintenance cards keep technical engine concepts behind drill-down", async ({ page }) => {
    await installWorkflowApi(page, { role: "operator" });
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.goto("/work", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "Team Findings" }).click();
    const cards = page.locator(".work-card-list");
    await expect(cards).toBeVisible();
    await expect(cards).not.toContainText(/coupling|relationship|correlation|provenance|lineage|raw signal|signed change|baseline value|current value/i);
  });
});
