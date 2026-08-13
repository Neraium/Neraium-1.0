import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, governedComparisonResult, test } from "./fixtures.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const screenshotDirectory = path.resolve(here, "../../../.planning/screenshots/shared-workspace-authorization");
const WORKSPACE_A = "ws-north-plant";
const WORKSPACE_B = "ws-south-plant";
const FINDING_ID = "finding-shared-pump";
const FINDING_KEY = "pump-response";
const SECRET_EVIDENCE = "North Plant proprietary bearing signature";

const users = {
  lead: { email: "morgan.lead@neraium.test", name: "Morgan Lead", role: "operator" },
  technician: { email: "taylor.tech@neraium.test", name: "Taylor Technician", role: "viewer" },
  engineer: { email: "alex.engineer@neraium.test", name: "Alex Engineer", role: "operator" },
  outsider: { email: "casey.south@neraium.test", name: "Casey South", role: "operator" },
};

const workspaceA = {
  workspace_id: WORKSPACE_A,
  display_name: "North Plant",
  kind: "facility",
  is_active: true,
};

const workspaceB = {
  workspace_id: WORKSPACE_B,
  display_name: "South Plant",
  kind: "facility",
  is_active: true,
};

function analyticalPayload() {
  const analysis = {
    analysis_id: "workspace-authorization-analysis",
    generated_at: "2026-08-13T08:00:00Z",
    systems: [{ id: "chw-loop", name: "North Plant · Chilled Water Loop" }],
    relationships: [{
      id: "pump-flow",
      columns: ["CHWP-2-SPD", "CHWP-2-FLOW"],
      change_type: "weakened",
      baseline_strength: 0.84,
      current_strength: 0.46,
      confidence: "qualified",
    }],
    insights: [{
      id: FINDING_KEY,
      title: "Pump discharge response changed",
      headline: "Pump discharge response is slower under comparable demand",
      confidence: "high",
      system: "North Plant · Chilled Water Loop",
      system_name: "North Plant · Chilled Water Loop",
      equipment_name: "CHWP-2 · Mechanical Room 2",
      what_changed: "Pump discharge response is slower under comparable demand.",
      why_it_matters: "The chilled-water loop is responding differently from its established behavior.",
      variables: ["CHWP-2-SPD", "CHWP-2-FLOW"],
      next_checks: ["Inspect CHWP-2 bearings and compare the local gauge."],
      recommended_investigation: [{
        rank: 1,
        check: "Inspect CHWP-2 bearings and compare the local gauge.",
        reason: "A field inspection can confirm whether the behavioral change has a physical correlate.",
        category: "physical_system",
        editable: true,
      }],
      supporting_evidence: [
        "The response change persisted across comparable operating windows.",
        SECRET_EVIDENCE,
      ],
      contributing_relationships: [{
        id: "pump-flow",
        columns: ["CHWP-2-SPD", "CHWP-2-FLOW"],
        change_type: "weakened",
        baseline_strength: 0.84,
        current_strength: 0.46,
      }],
      classification: {
        type: "unexplained_systemic_change",
        label: "Persistent operating change",
        confidence: "high",
        reasons: ["Comparable operating context supported the comparison."],
        alternative_explanations: ["An undocumented operating change may still explain the observation."],
        certainty_limit: "The evidence identifies a behavioral change, not its cause.",
      },
      data_confidence: { rating: "high", summary: "Recorded quality checks passed.", reasons: [] },
      operating_mode: {
        match: "strong",
        confidence: "high",
        baseline_mode_label: "Daytime mid-load",
        recent_mode_label: "Daytime mid-load",
        differences: [],
      },
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
        relationship_comparison: {
          metric: "pearson_correlation",
          baseline_value: 0.84,
          current_value: 0.46,
          signed_change: -0.38,
          absolute_change: 0.38,
          direction: "decreased",
        },
      },
      investigation_guidance: [{
        rank: 1,
        check: "Inspect CHWP-2 at Mechanical Room 2.",
        reason: "Confirm whether a physical condition accompanies the recorded change.",
        category: "physical_system",
        editable: true,
      }],
      activity_timeline: [{
        event_type: "baseline_reference",
        title: "Baseline reference period",
        start: "2026-08-01T08:00:00Z",
        end: "2026-08-02T08:00:00Z",
        precision: "range",
      }],
    }],
  };
  const result = governedComparisonResult({
    job_id: "workspace-authorization-run",
    facility_name: "North Plant",
    filename: "north-plant-comparison.csv",
    processed_at: "2026-08-13T08:00:00Z",
    sii_reliable_enough_to_show: true,
    sii_completed: true,
    data_quality: { coverage_percent: 96, warnings: [] },
    replay_timeline: { timeline: [{ timestamp: "2026-08-01T08:00:00Z" }, { timestamp: "2026-08-13T08:00:00Z" }] },
    analysis_result: analysis,
    analysis_explanation: analysis,
    baseline_analysis: { status: "available", relationship_drift: analysis.relationships },
    evidence_package: { id: "north-plant-package" },
  });
  const currentUpload = { job_id: result.job_id, filename: result.filename, status: "complete", result };
  return {
    status: "complete",
    session_state: "verified",
    sii_completed: true,
    latest_result: result,
    current_upload: currentUpload,
    snapshot: { status: "complete", sii_completed: true, current_upload: currentUpload, latest_result: result },
  };
}

function emptyAnalyticalPayload() {
  return {
    status: "not_found",
    session_state: "empty",
    sii_completed: false,
    latest_result: null,
    current_upload: null,
    snapshot: null,
  };
}

function workflow(overrides = {}) {
  return {
    version: 1,
    status: "open",
    recommended_priority: "high",
    user_priority: null,
    effective_priority: "high",
    assignment: null,
    assigned_by: "Morgan Lead",
    due_at: "2026-08-15T23:59:59Z",
    manager_note: "Begin with a visual and audible inspection while the pump is running.",
    latest_field_report: null,
    field_reports: [],
    resolution: null,
    updated_at: "2026-08-13T09:00:00Z",
    updated_by: users.lead.email,
    ...overrides,
  };
}

function finding(workflowOverrides = {}) {
  return {
    finding_id: FINDING_ID,
    source: {
      kind: "evidence_run",
      id: "workspace-authorization-run",
      run_id: "workspace-authorization-run",
      finding_key: FINDING_KEY,
    },
    evidence: {
      source_run_id: "workspace-authorization-run",
      source_finding_key: FINDING_KEY,
      recommended_priority: "high",
      finding: {
        headline: "Pump discharge response is slower under comparable demand",
        system_name: "North Plant · Chilled Water Loop",
        equipment_name: "CHWP-2 · Mechanical Room 2",
        what_changed: "Pump discharge response is slower under comparable demand.",
        why_it_matters: "The chilled-water loop is responding differently from its established behavior.",
        next_checks: ["Inspect CHWP-2 bearings and compare the local gauge."],
        confidence: "high",
      },
    },
    workflow: workflow(workflowOverrides),
    activity: { count: 2, latest_event_at: "2026-08-13T10:00:00Z", url: `/api/findings/${FINDING_ID}/activity` },
    created_at: "2026-08-13T08:00:00Z",
  };
}

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function sessionPayload(actor, workspace) {
  return {
    authenticated: true,
    user: actor,
    workspaces: [workspace],
    default_workspace_id: workspace.workspace_id,
  };
}

function isPublicRequest(pathname) {
  return pathname.startsWith("/api/health")
    || pathname.startsWith("/api/domain/mode")
    || pathname.startsWith("/api/intelligence/engine-identity");
}

async function installWorkspaceApi(page, {
  actor = users.lead,
  workspace = workspaceA,
  initialFinding = finding(),
} = {}) {
  const state = {
    actor,
    workspace,
    finding: initialFinding,
    mutations: [],
    protectedRequests: [],
  };
  const members = [
    { member_id: users.technician.email, display_name: users.technician.name, role: "viewer", is_active: true },
    { member_id: users.engineer.email, display_name: users.engineer.name, role: "operator", is_active: true },
    { member_id: users.lead.email, display_name: users.lead.name, role: "operator", is_active: true },
  ];
  const activity = [
    { label: "Finding detected", summary: "Neraium surfaced a persistent operating change.", actor: "Neraium", recorded_at: "2026-08-13T08:00:00Z", version: 0 },
  ];

  await page.addInitScript((workspaceId) => {
    window.localStorage.setItem("neraium.current_workspace_id", workspaceId);
  }, workspace.workspace_id);

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const workspaceHeader = request.headers()["x-neraium-workspace-id"] ?? "";
    if (!isPublicRequest(url.pathname)) {
      state.protectedRequests.push({ method: request.method(), pathname: url.pathname, workspaceHeader });
    }
    const authorized = workspaceHeader === state.workspace.workspace_id;

    if (url.pathname === "/api/auth/me") return json(route, sessionPayload(state.actor, state.workspace));
    if (url.pathname === "/api/health") return json(route, { status: "ok" });
    if (url.pathname === "/api/ready") return json(route, { status: "ready", ready: { status: "ready" } });
    if (url.pathname === "/api/domain/mode") return json(route, { mode: "hvac", domain: "hvac" });
    if (url.pathname === "/api/intelligence/engine-identity") return json(route, { engine: "sii", version: "e2e" });
    if (url.pathname === "/api/data/latest-upload") return json(route, authorized && state.workspace.workspace_id === WORKSPACE_A ? analyticalPayload() : emptyAnalyticalPayload());
    if (url.pathname === "/api/facility/context") return json(route, authorized && state.workspace.workspace_id === WORKSPACE_A ? {
      systems: [{ system_id: "chw-loop", name: "North Plant · Chilled Water Loop" }],
      equipment: [{ id: "chwp-2", name: "CHWP-2", system_id: "chw-loop", location: "Mechanical Room 2" }],
      signal_mappings: [
        { raw_tag: "CHWP-2-SPD", normalized_name: "pump_speed", alias: "CHWP-2 speed", system_id: "chw-loop" },
        { raw_tag: "CHWP-2-FLOW", normalized_name: "pump_flow", alias: "CHWP-2 discharge flow", system_id: "chw-loop" },
      ],
    } : { systems: [], equipment: [], signal_mappings: [] });
    if (url.pathname === "/api/facility/systems") return json(route, { systems: [] });
    if (url.pathname === "/api/evidence/runs") return json(route, { runs: [] });
    if (url.pathname.startsWith("/api/evidence/packages/") && url.pathname.endsWith("/related")) {
      return authorized && state.workspace.workspace_id === WORKSPACE_A
        ? json(route, { package_id: "north-plant-package", related: [], limitations: [] })
        : json(route, { detail: "Evidence unavailable" }, 404);
    }

    if (url.pathname === "/api/findings/members") {
      return authorized && state.workspace.workspace_id === WORKSPACE_A
        ? json(route, { members })
        : json(route, { members: [] });
    }
    if (url.pathname.startsWith("/api/findings")) {
      const parts = url.pathname.split("/").filter(Boolean);
      const findingId = parts[2] ?? "";
      const endpoint = parts[3] ?? "";
      const canReadFinding = authorized && state.workspace.workspace_id === WORKSPACE_A && findingId === FINDING_ID;
      if (findingId && !canReadFinding) return json(route, { detail: "Finding unavailable" }, 404);
      if (findingId && endpoint === "activity") return json(route, { activity });
      if (findingId && endpoint === "workflow" && request.method() === "PATCH") {
        const body = request.postDataJSON();
        state.mutations.push({ actor: state.actor.email, endpoint, body });
        state.finding.workflow = {
          ...state.finding.workflow,
          version: state.finding.workflow.version + 1,
          status: body.status ?? state.finding.workflow.status,
          user_priority: Object.hasOwn(body, "user_priority") ? body.user_priority : state.finding.workflow.user_priority,
          effective_priority: Object.hasOwn(body, "user_priority") ? body.user_priority ?? state.finding.workflow.recommended_priority : state.finding.workflow.effective_priority,
          assignment: Object.hasOwn(body, "assignment") ? body.assignment : state.finding.workflow.assignment,
          due_at: Object.hasOwn(body, "due_at") ? body.due_at : state.finding.workflow.due_at,
          manager_note: Object.hasOwn(body, "manager_note") ? body.manager_note : state.finding.workflow.manager_note,
          updated_by: state.actor.email,
        };
        activity.push({
          label: body.assignment ? "Finding assigned" : "Work status changed",
          summary: body.assignment ? `Assigned to ${body.assignment.label}.` : `Status changed to ${body.status}.`,
          actor: state.actor.name,
          recorded_at: "2026-08-13T11:00:00Z",
          version: state.finding.workflow.version,
        });
        return json(route, state.finding);
      }
      if (findingId && endpoint === "field-reports" && request.method() === "POST") {
        const body = request.postDataJSON();
        state.mutations.push({ actor: state.actor.email, endpoint, body });
        const report = { ...body, actor: state.actor.name, recorded_at: "2026-08-13T11:30:00Z" };
        state.finding.workflow = {
          ...state.finding.workflow,
          version: state.finding.workflow.version + 1,
          status: body.needs_escalation ? "escalated" : body.investigation_complete ? "awaiting_review" : state.finding.workflow.status,
          latest_field_report: report,
          field_reports: [...state.finding.workflow.field_reports, report],
          updated_by: state.actor.email,
        };
        activity.push({
          label: "Field report added",
          summary: `${state.actor.name} recorded the field investigation.`,
          actor: state.actor.name,
          recorded_at: report.recorded_at,
          version: state.finding.workflow.version,
        });
        return json(route, state.finding);
      }
      if (findingId && !endpoint) return json(route, state.finding);

      let items = authorized && state.workspace.workspace_id === WORKSPACE_A ? [state.finding] : [];
      if (url.searchParams.get("assigned_to_me") === "true") {
        items = items.filter((item) => item.workflow.assignment?.external_ref === state.actor.email);
      }
      if (url.searchParams.get("unassigned") === "true") items = items.filter((item) => !item.workflow.assignment);
      if (url.searchParams.get("active") === "true") items = items.filter((item) => !["resolved", "dismissed"].includes(item.workflow.status));
      return json(route, { findings: items, limit: 30, offset: 0, has_more: false, next_offset: null });
    }

    return json(route, {});
  });
  return state;
}

function expectWorkspaceHeaders(state, workspaceId) {
  expect(state.protectedRequests.length).toBeGreaterThan(0);
  expect(state.protectedRequests.filter((request) => request.workspaceHeader !== workspaceId)).toEqual([]);
}

async function completeTechnicianWork(page) {
  const brief = page.locator(".work-brief");
  await brief.getByRole("button", { name: "Accept work" }).click();
  await brief.getByRole("button", { name: "Start investigation" }).click();
  await brief.getByLabel("What did you inspect?").fill("Coupling guard, bearings, seals, and local discharge gauge");
  await brief.getByLabel("What did you find?").fill("Light bearing vibration; no visible leak or abnormal heat");
  await brief.getByLabel("Action taken, if any").fill("Secured the loose coupling guard fastener");
  await brief.getByLabel("Yes", { exact: true }).check();
  await brief.getByLabel("Additional note").fill("Vibration reduced after the guard was secured.");
  await brief.getByLabel("My investigation is complete").check();
  await brief.getByRole("button", { name: "Send for review" }).click();
  await expect(page.locator(".work-brief__urgency").getByText("Awaiting review", { exact: true })).toBeVisible();
}

test.describe("Facility workspace authorization", () => {
  test.beforeAll(() => mkdirSync(screenshotDirectory, { recursive: true }));

  test("lead assigns an active member and that technician completes the shared work", async ({ page }) => {
    const state = await installWorkspaceApi(page);
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.goto("/work", { waitUntil: "domcontentloaded" });
    await expect(page.getByText("Facility workspace · North Plant")).toBeVisible();
    await page.getByRole("button", { name: "Team Findings" }).click();
    await page.getByRole("button", { name: "Needs assignment" }).click();
    await page.getByRole("button", { name: /Open CHWP-2/ }).click();

    const leadControls = page.locator(".lead-controls");
    await expect(leadControls.getByLabel("Assign to").locator("option")).toHaveCount(4);
    await expect(leadControls.getByLabel("Assign to").locator(`option[value="${users.outsider.email}"]`)).toHaveCount(0);
    await leadControls.getByLabel("Assign to").selectOption(users.technician.email);
    await leadControls.getByLabel("Guidance for the technician").fill("Inspect bearings first and notify the lead if vibration is severe.");
    await leadControls.getByRole("button", { name: "Save work details" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Assignment and guidance saved." })).toBeVisible();
    expect(state.mutations.at(-1)).toMatchObject({
      actor: users.lead.email,
      endpoint: "workflow",
      body: {
        assignment: {
          target_type: "person",
          label: users.technician.name,
          external_ref: users.technician.email,
        },
      },
    });
    await page.screenshot({ path: path.join(screenshotDirectory, "lead-assignment-desktop.png"), fullPage: true });

    state.actor = users.technician;
    await page.goto("/work", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("button", { name: "My Work" })).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("button", { name: /Open CHWP-2/ }).click();
    await expect(page.getByText("Inspect bearings first and notify the lead if vibration is severe.")).toBeVisible();
    await completeTechnicianWork(page);
    expect(state.mutations.find((mutation) => mutation.endpoint === "field-reports")).toMatchObject({
      actor: users.technician.email,
      body: { investigation_complete: true, needs_escalation: false },
    });
    await page.screenshot({ path: path.join(screenshotDirectory, "technician-complete-desktop.png"), fullPage: true });
    expectWorkspaceHeaders(state, WORKSPACE_A);
  });

  test("engineer opens the same finding investigation and evidence", async ({ page }) => {
    const state = await installWorkspaceApi(page, {
      actor: users.engineer,
      initialFinding: finding({
        version: 4,
        status: "awaiting_review",
        assignment: { target_type: "person", label: users.technician.name, external_ref: users.technician.email },
      }),
    });
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.goto(`/work/${FINDING_ID}`, { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "Open investigation" }).click();
    await expect(page).toHaveURL(new RegExp(`/investigations/${FINDING_KEY}$`));
    await expect(page.getByText("Investigation guidance")).toBeVisible();
    await page.getByRole("button", { name: "Open evidence record" }).click();
    await expect(page).toHaveURL(new RegExp(`/evidence/${FINDING_KEY}$`));
    await expect(page.getByRole("heading", { name: "Source lineage" })).toBeVisible();
    await expect(page.getByText("CHWP-2-SPD / CHWP-2-FLOW")).toBeVisible();
    await expect(page.getByText(SECRET_EVIDENCE)).toBeVisible();
    await page.screenshot({ path: path.join(screenshotDirectory, "engineer-evidence-desktop.png"), fullPage: true });
    expectWorkspaceHeaders(state, WORKSPACE_A);
  });

  test("user in another workspace is denied finding and evidence deep links without metadata leakage", async ({ page }) => {
    const state = await installWorkspaceApi(page, { actor: users.outsider, workspace: workspaceB });
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.goto(`/work/${FINDING_ID}`, { waitUntil: "domcontentloaded" });
    const workDenial = page.getByRole("alert").filter({ hasText: "Finding unavailable" });
    await expect(workDenial).toBeVisible();
    await expect(workDenial).toContainText("current facility workspace");
    await expect(page.locator("#forensic-main")).not.toContainText("North Plant");
    await expect(page.locator("#forensic-main")).not.toContainText(SECRET_EVIDENCE);

    await page.goto(`/evidence/${FINDING_KEY}`, { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Finding unavailable" })).toBeVisible();
    await expect(page.getByText("This finding is unavailable in the current facility workspace.")).toBeVisible();
    await expect(page.locator("#forensic-main")).not.toContainText("North Plant");
    await expect(page.locator("#forensic-main")).not.toContainText(SECRET_EVIDENCE);
    await expect(page.locator("#forensic-main")).not.toContainText("Evidence records");
    await page.screenshot({ path: path.join(screenshotDirectory, "unauthorized-workspace-denial.png"), fullPage: true });
    expectWorkspaceHeaders(state, WORKSPACE_B);
  });

  test("390px technician can execute assigned work inside the facility workspace", async ({ page }) => {
    const state = await installWorkspaceApi(page, {
      actor: users.technician,
      initialFinding: finding({
        assignment: { target_type: "person", label: users.technician.name, external_ref: users.technician.email },
      }),
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/work/${FINDING_ID}`, { waitUntil: "domcontentloaded" });
    const brief = page.locator(".work-brief");
    await expect(brief).toBeVisible();
    await expect(brief.getByRole("heading", { name: "CHWP-2 · Mechanical Room 2" })).toBeVisible();
    await expect(brief.getByText(users.technician.name)).toBeVisible();
    const accept = brief.getByRole("button", { name: "Accept work" });
    expect(await accept.evaluate((node) => node.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    await accept.click();
    await brief.getByRole("button", { name: "Start investigation" }).click();
    await page.evaluate(() => document.activeElement?.blur());
    await page.screenshot({ path: path.join(screenshotDirectory, "technician-390.png"), fullPage: true });
    await brief.getByLabel("What did you inspect?").fill("Bearings and local gauge");
    await brief.getByLabel("What did you find?").fill("No leak; slight vibration");
    await brief.getByLabel("No obvious problem", { exact: true }).check();
    await brief.getByLabel("My investigation is complete").check();
    await brief.getByRole("button", { name: "Send for review" }).click();
    await expect(page.locator(".work-brief__urgency").getByText("Awaiting review", { exact: true })).toBeVisible();
    const widths = await page.evaluate(() => ({ viewport: innerWidth, root: document.documentElement.scrollWidth, body: document.body.scrollWidth }));
    expect(widths.root).toBeLessThanOrEqual(widths.viewport + 1);
    expect(widths.body).toBeLessThanOrEqual(widths.viewport + 1);
    expectWorkspaceHeaders(state, WORKSPACE_A);
  });
});
