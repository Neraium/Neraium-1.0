/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import EngineeringReasoningWorkspace from "./EngineeringReasoningWorkspace";

function analysisResult(overrides = {}) {
  const analysis = {
    systems: [{ id: "cooling", name: "Cooling system" }],
    relationships: [{
      id: "rel-1",
      columns: ["Condenser approach temperature", "Compressor current"],
      change_type: "changed",
      baseline_strength: 0.094013,
      current_strength: 0.833811,
      correlation_delta: 0.739798,
    }],
    insights: [{
      id: "finding-1",
      title: "Condenser performance changed",
      system: "Cooling system",
      subsystem: "Condenser Water",
      asset: "Chiller 03",
      confidence: "high",
      what_changed: "Condenser-side performance changed during comparable operation.",
      why_it_matters: "The response differs from the learned operating pattern.",
      recommended_check: "Verify pressure transmitter.",
      variables: ["Condenser approach temperature", "Compressor current"],
      supporting_evidence: [
        "Condenser approach temperature increased 15.3%.",
        "Compressor current increased 5.5%.",
        "The relationship moved outside its learned range.",
      ],
      contributing_relationships: [{
        id: "rel-1",
        columns: ["Condenser approach temperature", "Compressor current"],
        change_type: "changed",
        baseline_strength: 0.094013,
        current_strength: 0.833811,
        correlation_delta: 0.739798,
      }],
      classification: { type: "unexplained_systemic_change", confidence: "high", reasons: ["The relationship remained outside learned behavior."] },
      data_confidence: { rating: "high", summary: "Telemetry passed the recorded checks." },
      operating_mode: { match: "strong", confidence: "high", baseline_mode_label: "Mid-load", recent_mode_label: "Mid-load" },
      persistence: { persistent: true, duration: "3 days", summary: "The shift persisted across comparable windows." },
      investigation_guidance: [
        { rank: 1, check: "Verify pressure transmitter.", reason: "Source validation bounds the interpretation.", category: "instrumentation" },
        { rank: 2, check: "Review the affected pressure boundary.", reason: "The mapped relationship changed there.", category: "physical_system" },
        { rank: 3, check: "Confirm the active control state.", reason: "Comparable operation is required.", category: "controls" },
        { rank: 4, check: "Compare the next operating window.", reason: "A follow-up window tests persistence.", category: "operating_context" },
      ],
      activity_timeline: [{ event_type: "persistence_supported", title: "Persistence supported", period_label: "Three comparable windows" }],
      alternative_explanations: ["An undocumented control change may explain the shift."],
      certainty_limit: "The evidence does not establish a cause.",
    }],
    ...overrides.analysis,
  };
  return {
    facility_name: "North Plant",
    workflow: "analyze_new_data",
    status: "COMPLETE",
    processing_state: "complete",
    portfolio_id: "default",
    system_id: "default",
    baseline_id: "baseline-42",
    baseline_dataset_id: "baseline-dataset-42",
    comparison_dataset_id: "comparison-dataset-42",
    comparison_analysis_id: "run-42",
    analysis_run_id: "run-42",
    dataset_id: "comparison-dataset-42",
    active_baseline_reference: { model_id: "baseline-42", dataset_id: "baseline-dataset-42" },
    job_id: "run-42",
    processed_at: new Date().toISOString(),
    sii_completed: true,
    sii_reliable_enough_to_show: true,
    data_quality: { coverage_percent: 82, warnings: ["Historian X was unavailable.", "3 dropped rows."] },
    data_gaps: [{ id: "gap-1", source: "Historian X", signals: ["Efficiency"] }],
    baseline_analysis: { status: "available", relationship_drift: analysis.relationships },
    analysis_explanation: analysis,
    ...overrides.result,
  };
}

function renderWorkspace({ path = "/sites/current", result = analysisResult(), apiFetch = vi.fn(), onWorkspaceNavigate = vi.fn(), onWorkspaceChange = vi.fn(), workspaceSession = null, currentWorkspace = null, role = "operator" } = {}) {
  window.history.replaceState({}, "", path);
  const props = {
    liveOps: {},
    canonicalFinding: { exists: false },
    currentSession: {},
    effectiveLatestUploadResult: result,
    effectiveLatestUploadSnapshot: result ? { status: "complete", sii_completed: true } : {},
    apiFetch,
    onWorkspaceNavigate,
    onWorkspaceChange,
    workspaceSession,
    currentWorkspace,
    currentUser: { name: "Engineer One", email: "engineer@neraium.test", role },
  };
  return { ...render(React.createElement(EngineeringReasoningWorkspace, props)), onWorkspaceNavigate, onWorkspaceChange };
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.history.replaceState({}, "", "/");
});

describe("EngineeringReasoningWorkspace daily workflows", () => {
  it("switches among explicit facility workspaces from compact workspace controls", () => {
    const onWorkspaceChange = vi.fn();
    renderWorkspace({
      onWorkspaceChange,
      workspaceSession: { workspaces: [{ workspace_id: "default", display_name: "Personal workspace", is_active: true }, { workspace_id: "ws-north", display_name: "North Plant", is_active: true }] },
      currentWorkspace: { workspace_id: "ws-north", display_name: "North Plant" },
    });
    const selector = screen.getByLabelText("Current facility workspace");
    expect(selector.value).toBe("ws-north");
    fireEvent.change(selector, { target: { value: "default" } });
    expect(onWorkspaceChange).toHaveBeenCalledWith("default");
  });

  it.each(["investigations", "evidence"])("never falls back to a default finding for an unknown %s deep link", async (routeName) => {
    const apiFetch = vi.fn(async () => ({ ok: true, json: async () => ({ runs: [] }) }));
    renderWorkspace({ path: `/${routeName}/workspace-b-secret`, apiFetch });
    expect(await screen.findByRole("heading", { name: "Finding unavailable" })).toBeTruthy();
    expect(screen.getByText("This finding is unavailable in the current facility workspace.")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Chiller 03 changed" })).toBeNull();
    expect(document.body.textContent).not.toContain("workspace-b-secret");
  });

  it("launches first-baseline onboarding instead of an analytical empty dashboard", () => {
    const { onWorkspaceNavigate } = renderWorkspace({ result: null });
    expect(screen.getByTestId("first-baseline-experience")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Create Your First Baseline" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Import Historical Dataset" }));
    expect(onWorkspaceNavigate).toHaveBeenCalledWith("data-connections");
  });

  it("lets the operator exit onboarding into the baseline-needed workspace", () => {
    renderWorkspace({ result: null });
    fireEvent.click(screen.getByRole("button", { name: "Go to workspace" }));
    expect(screen.getByTestId("workspace-state-noDataset")).toBeTruthy();
    expect(screen.getByText(/Operations Brief · Baseline Needed/)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "No baseline available" })).toBeTruthy();
  });

  it("withholds the Operations Brief for baseline-only, legacy, or incomplete data", () => {
    const invalidResults = [
      { workflow: "create_baseline", status: "COMPLETE", processing_state: "complete", baseline_id: "baseline-42" },
      { ...analysisResult(), workflow: "legacy_analysis" },
      { ...analysisResult(), status: "PROCESSING", processing_state: "processing", sii_completed: false },
    ];
    for (const result of invalidResults) {
      const view = renderWorkspace({ result });
      expect(screen.queryByTestId("operations-brief")).toBeNull();
      view.unmount();
    }
  });

  it("opens on a restrained Operations Brief and hides empty sections", () => {
    renderWorkspace();
    expect(screen.getByTestId("operations-brief")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "North Plant" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "New" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Monitoring" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Needs attention" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Recently resolved" })).toBeNull();
    expect(screen.queryByText("New findings")).toBeNull();
    expect(screen.getByText("1 new finding for review.")).toBeTruthy();
  });

  it("keeps the alert scannable and progressively discloses evidence", () => {
    renderWorkspace();
    const card = screen.getByTestId("compact-finding-card");
    const finding = within(card);
    expect(finding.getByText("Cooling system")).toBeTruthy();
    expect(finding.getByRole("heading", { name: "Chiller 03 changed" })).toBeTruthy();
    expect(finding.getByText("Equipment / system")).toBeTruthy();
    expect(finding.getByText("Requested next action")).toBeTruthy();
    for (const label of ["Priority", "Assignment", "Due", "Workflow"]) expect(finding.getByText(label)).toBeTruthy();
    expect(finding.queryByText("Condenser approach temperature increased 15.3%.")).toBeNull();
    expect(finding.queryByText("Compressor current increased 5.5%.")).toBeNull();
    expect(finding.getByRole("button", { name: "Review" })).toBeTruthy();
    expect(finding.getByText("More actions")).toBeTruthy();
    expect(card.querySelector(".operational-finding__more").open).toBe(false);
  });

  it("renders a corroborated condition as the primary engineering object", () => {
    const supportingRelationships = [
      { id: "rel-1", columns: ["Pump power", "Flow"], change_type: "weakened", baseline_strength: 0.9, current_strength: 0.3 },
      { id: "rel-2", columns: ["Flow", "Discharge pressure"], change_type: "weakened", baseline_strength: 0.84, current_strength: 0.28 },
      { id: "rel-3", columns: ["Discharge pressure", "Pump speed"], change_type: "weakened", baseline_strength: 0.81, current_strength: 0.24 },
    ];
    const condition = {
      object_type: "condition",
      condition_id: "condition-pump",
      id: "condition-pump",
      headline: "Pump response weakening in Rush Tower water system",
      status: "open",
      confidence: "high",
      classification: { type: "unexplained_systemic_change", confidence: "high", reasons: ["Comparable operating evidence supports the condition."] },
      data_confidence: { rating: "high", summary: "Telemetry passed the recorded checks." },
      operating_mode: { match: "strong", confidence: "high", baseline_mode_label: "Two pumps", recent_mode_label: "Two pumps" },
      affected_systems: ["Pumping System"],
      affected_boundaries: ["Discharge boundary"],
      affected_signals: ["Pump power", "Flow", "Discharge pressure", "Pump speed"],
      localization: { system: "Pumping System", monitored_boundary: "Discharge boundary", likely_investigation_area: "Discharge boundary" },
      trajectory: { state: "Strengthening", scope: "evidence_support", evidence_window_duration: "18 days", corroboration_change: "Corroboration increased from 2 to 3 relationships", persistence: 0.85 },
      corroboration: { corroboration_strength: "moderate", relationship_count: 3 },
      comparable_operation: { status: "supported", comparable_period_count: 18, normal_behavior: "Pressure increased with pump speed.", current_behavior: "Pressure response weakened." },
      supporting_relationships: supportingRelationships,
      supporting_evidence: [
        "3 relationship changes align through flow and discharge pressure.",
        "Pump power and flow coupling changed from strong to weak.",
        "Corroboration increased from 2 to 3 relationships.",
      ],
      next_checks: ["Verify source data and inspect the affected pressure boundary."],
      recommended_investigation: [
        { rank: 1, check: "Verify source data and inspect the affected pressure boundary.", category: "source_validation" },
      ],
      timeline: [
        { event_type: "condition_evidence_window", title: "Condition evidence observed", period_label: "Recent comparison window" },
        { event_type: "evidence_trend_classified", title: "Evidence trend: Strengthening", start: "2026-07-01T00:00:00Z", end: "2026-07-19T00:00:00Z" },
      ],
    };
    renderWorkspace({ result: analysisResult({ analysis: { conditions: [condition] } }) });

    const card = screen.getByTestId("compact-finding-card");
    const view = within(card);
    expect(view.getByRole("heading", { name: "Discharge boundary changed" })).toBeTruthy();
    expect(view.getByText("Pumping System")).toBeTruthy();
    expect(view.queryByText(/relationship decreased/i)).toBeNull();
    expect(card.querySelector(".operational-finding__evidence")).toBeNull();
    expect(view.getByRole("button", { name: "Investigate" })).toBeTruthy();
    expect(view.getByText("Actions")).toBeTruthy();

    fireEvent.click(view.getByRole("button", { name: "Investigate" }));
    expect(window.location.pathname).toBe("/findings/condition-pump");
    expect(screen.getAllByText("Support trend").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Open investigation" }));
    expect(screen.getByRole("heading", { name: "Support trend" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Comparable operation" })).toBeTruthy();
    expect(screen.getByText("18 comparable periods")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Condition timeline" })).toBeTruthy();
  });

  it("keeps context-limited finding review concise and semantically consistent", () => {
    const condition = {
      object_type: "condition",
      condition_id: "condition-cooling",
      headline: "Cooling Distribution response weakening",
      status: "open",
      confidence: "moderate",
      confidence_score: 0.55,
      classification: { type: "context_limited_relationship_change", confidence: "limited", reasons: ["Operating conditions differed from baseline."] },
      data_confidence: { rating: "limited", summary: "Telemetry coverage limits comparison." },
      operating_mode: { match: "weak", confidence: "limited" },
      persistence: { persistent: false, status: "not_established", summary: "Persistence is not established by the available evidence windows." },
      trajectory: { state: "Strengthening", scope: "evidence_support", evidence_window_duration: "20 days 19 hours 55 minutes", persistence: 0.35 },
      corroboration: { corroboration_strength: "limited", relationship_count: 2 },
      comparable_operation: { status: "unavailable", evidence_summary: "No historical windows matched the observed operating context with enough paired samples." },
      affected_systems: ["Cooling Distribution"],
      affected_signals: ["chw_return_temp_f", "chiller_power_kw", "chiller_amp"],
      what_changed: "chw_return_temp_f / chiller_power_kw changed from strong to weak coupling. A second related relationship changed in the same evidence window.",
      why_it_matters: "Two connected changes moved together. Evidence is strengthening, but like-for-like comparability is limited.",
      supporting_relationships: [
        { id: "rel-1", columns: ["chw_return_temp_f", "chiller_power_kw"], change_type: "weakened", baseline_strength: 0.88, current_strength: 0.2 },
        { id: "rel-2", columns: ["chiller_power_kw", "chiller_amp"], change_type: "weakened", baseline_strength: 0.8, current_strength: 0.25 },
      ],
      supporting_evidence: [
        "chw_return_temp_f / chiller_power_kw changed from strong to weak coupling.",
        "2 corroborating relationships.",
        "Recent operating conditions differed from baseline.",
      ],
      next_checks: [
        "Verify return temperature, power, and amp data.",
        "Review load and staging during the evidence window.",
        "Compare operator logs and setpoint changes with the evidence window.",
        "This fourth action must not appear.",
      ],
    };
    renderWorkspace({ result: analysisResult({ analysis: { conditions: [condition] } }) });

    expect(screen.getByRole("heading", { name: "Cooling Distribution changed" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Investigate" }));

    expect(screen.getByText("Context-limited relationship change")).toBeTruthy();
    expect(screen.getAllByText("Not established").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Support trend").length).toBeGreaterThan(0);
    expect(screen.getByText("Increasing")).toBeTruthy();
    expect(screen.getByText("Evidence support is increasing, but like-for-like comparability is limited.")).toBeTruthy();
    expect(screen.queryByText(/^Trajectory$/)).toBeNull();
    expect(screen.queryByText(/Observed for 81 days/i)).toBeNull();
    expect(screen.getByText("Return temperature signal / Power signal changed from strong to weak coupling.")).toBeTruthy();
    expect(document.querySelectorAll(".case-sections--review .classification-guidance > li")).toHaveLength(3);
    expect(screen.queryByText("This fourth action must not appear.")).toBeNull();
    const headings = [...document.querySelectorAll(".case-sections--review > section > h2")].map((node) => node.textContent);
    expect(headings).toEqual(["What changed", "Why it matters", "What to check first", "Key evidence"]);
    for (const paragraph of document.querySelectorAll(".case-sections--review p")) {
      expect(paragraph.textContent.length).toBeLessThanOrEqual(260);
    }
  });

  it("moves an acknowledged investigation out of New without changing classification", async () => {
    renderWorkspace();
    fireEvent.click(screen.getByText("More actions"));
    fireEvent.click(screen.getByRole("button", { name: "I’m checking this" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "New" })).toBeNull());
    expect(screen.getByRole("heading", { name: "Monitoring" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "I’m checking this" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    expect(screen.getByText("Unexplained systemic change")).toBeTruthy();
  });

  it("normalizes a known condition into the existing feedback endpoint", async () => {
    const apiFetch = vi.fn(async (url) => String(url).includes("/feedback")
      ? { ok: true, json: async () => ({ latest_feedback_category: "expected_behavior" }) }
      : { ok: true, json: async () => ({ runs: [] }) });
    renderWorkspace({ apiFetch });
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    fireEvent.click(screen.getByRole("button", { name: "Known or explained" }));
    expect(screen.getByLabelText("Known condition")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save explanation" }));
    await waitFor(() => expect(screen.getByText("Explained.")).toBeTruthy());
    const feedbackCall = apiFetch.mock.calls.find(([url]) => String(url).includes("/feedback"));
    expect(feedbackCall[0]).toBe("/api/evidence/runs/run-42/feedback");
    expect(JSON.parse(feedbackCall[1].body)).toEqual({ category: "expected_behavior", outcome: "Scheduled staging change", note: "Scheduled staging change" });
    expect(screen.getAllByText("Explained").length).toBeGreaterThan(0);
  });

  it("records Not useful as presentation feedback without altering evidence", async () => {
    const apiFetch = vi.fn(async (url) => String(url).includes("/feedback")
      ? { ok: true, json: async () => ({ latest_feedback_category: "nothing_meaningful" }) }
      : { ok: true, json: async () => ({ runs: [] }) });
    renderWorkspace({ apiFetch });
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    fireEvent.click(screen.getByRole("button", { name: "Not useful" }));
    await waitFor(() => expect(screen.getByText("Not useful.")).toBeTruthy());
    expect(screen.getByText("Unexplained systemic change")).toBeTruthy();
    const feedbackCall = apiFetch.mock.calls.find(([url]) => String(url).includes("/feedback"));
    expect(JSON.parse(feedbackCall[1].body)).toEqual({ category: "nothing_meaningful", outcome: "Not useful", note: null });
  });

  it("orders finding review around change, importance, checks, timeline, and evidence", () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    expect(window.location.pathname).toBe("/findings/finding-1");
    const headings = [...document.querySelectorAll(".case-sections--review > section > h2")].map((node) => node.textContent);
    expect(headings).toEqual(["What changed", "Why it matters", "What to check first", "Key evidence"]);
    expect(screen.getAllByRole("button", { name: "I’m checking this" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Open investigation" })).toBeTruthy();
  });

  it("opens a progressive investigation and keeps technical depth collapsed", () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    fireEvent.click(screen.getByRole("button", { name: "Open investigation" }));
    expect(window.location.pathname).toBe("/investigations/finding-1");
    const headings = [...document.querySelectorAll(".case-sections--investigation > section > h2")].map((node) => node.textContent);
    expect(headings).toEqual(["Finding summary", "Relationship timeline", "Supporting evidence", "Investigation guidance", "Current review state"]);
    for (const label of ["Operating-mode evidence", "Sensor-health evidence", "Alternative explanations", "Certainty limits", "Data limitations", "Source lineage", "Audit and replay information"]) {
      expect(screen.getByText(label).closest("details").open).toBe(false);
    }
  });

  it("moves directly from finding to investigation to the evidence record", () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    fireEvent.click(screen.getByRole("button", { name: "Open investigation" }));
    fireEvent.click(screen.getByRole("button", { name: "Open evidence record" }));
    expect(window.location.pathname).toBe("/evidence/finding-1");
    expect(screen.getByTestId("evidence-record")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Source lineage" })).toBeTruthy();
    expect(screen.getByText("Metric")).toBeTruthy();
    expect(screen.getByText("Signed change")).toBeTruthy();
    expect(screen.getByText("Absolute change")).toBeTruthy();
  });

  it("supports direct workflow navigation and keyboard search", () => {
    renderWorkspace();
    const navigation = screen.getByRole("navigation", { name: "Primary navigation" });
    for (const label of ["System Status", "Live Monitoring", "Systems", "Findings", "Evidence & Outcomes", "Data"]) expect(within(navigation).getByRole("button", { name: label })).toBeTruthy();
    fireEvent.click(within(navigation).getByRole("button", { name: "Evidence & Outcomes" }));
    expect(window.location.pathname).toBe("/investigations");
    fireEvent.click(within(navigation).getByRole("button", { name: "Systems" }));
    expect(screen.getByRole("heading", { name: "North Plant" })).toBeTruthy();
    const search = screen.getByRole("combobox", { name: /Search sites/i });
    fireEvent.change(search, { target: { value: "Cooling system" } });
    fireEvent.keyDown(search, { key: "Enter" });
    expect(screen.getByRole("heading", { name: "Cooling system" })).toBeTruthy();
  });

  it("routes canonical shared work independently and preserves engineer drill-down", async () => {
    const workCase = {
      finding_id: "canonical-work-1",
      source: { kind: "evidence_run", id: "run-42", finding_key: "finding-1", run_id: "run-42" },
      evidence: { finding: { headline: "Chiller 03 changed", system_name: "Cooling system", equipment_name: "Chiller 03", next_checks: ["Inspect the condenser approach first."], confidence: "high" } },
      workflow: { version: 1, status: "investigating", effective_priority: "high", assignment: { target_type: "person", label: "Engineer One", external_ref: "engineer@neraium.test" } },
      activity: { count: 0 },
    };
    const apiFetch = vi.fn(async (url) => {
      const path = String(url);
      if (path.startsWith("/api/findings?")) return { ok: true, json: async () => ({ findings: [workCase], has_more: false }) };
      if (path === "/api/findings/members") return { ok: true, json: async () => ({ members: [] }) };
      if (path.endsWith("/activity")) return { ok: true, json: async () => ({ activity: [] }) };
      if (path.startsWith("/api/evidence/runs?")) return { ok: true, json: async () => ({ runs: [] }) };
      return { ok: true, json: async () => ({}) };
    });
    renderWorkspace({ path: "/work", apiFetch });
    const navigation = screen.getByRole("navigation", { name: "Primary navigation" });
    expect(within(navigation).getByRole("button", { name: "Work" }).getAttribute("aria-current")).toBe("page");
    fireEvent.click(await screen.findByRole("button", { name: /Open Chiller 03/i }));
    expect(window.location.pathname).toBe("/work/canonical-work-1");
    fireEvent.click(await screen.findByRole("button", { name: "Open investigation" }));
    expect(window.location.pathname).toBe("/investigations/finding-1");
    expect(screen.getByRole("heading", { name: "Supporting evidence" })).toBeTruthy();
  });

  it("speaks confidently when the completed analysis has no meaningful changes", () => {
    const result = analysisResult({ analysis: { insights: [] }, result: { data_gaps: [], data_quality: { coverage_percent: 100, warnings: [] } } });
    renderWorkspace({ result });
    expect(screen.getByText("All monitored systems are within learned behavior.")).toBeTruthy();
    expect(screen.getByText("No new findings require review.")).toBeTruthy();
    expect(screen.queryByText("Evidence insufficient")).toBeNull();
  });

  it("keeps the multi-site portfolio available without replacing the default brief", async () => {
    const apiFetch = vi.fn(async () => ({ ok: true, json: async () => ({ runs: [{ run_id: "site-b-run", adaptive_site_key: "site-b", site_name: "South Plant", system_name: "Pumping", rows_received: 10, rows_accepted: 10, evidence_summary: [], observation_status: "normal", baseline_status: "Established" }] }) }));
    renderWorkspace({ apiFetch });
    expect(await screen.findByRole("button", { name: "Sites" })).toBeTruthy();
    expect(screen.getByTestId("operations-brief")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Sites" }));
    expect(screen.getByRole("heading", { name: "Sites" })).toBeTruthy();
  });
});
