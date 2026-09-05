/* @vitest-environment jsdom */
import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
      finding_confidence_v1: {
        relationship_comparison: {
          metric: "pearson_correlation",
          baseline_value: 0.094013,
          current_value: 0.833811,
          signed_change: 0.739798,
          absolute_change: 0.739798,
          direction: "increased",
        },
      },
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
    evidence_persisted: true,
    data_quality: { coverage_percent: 82, warnings: ["Historian X was unavailable.", "3 dropped rows."] },
    data_gaps: [{ id: "gap-1", source: "Historian X", signals: ["Efficiency"] }],
    baseline_analysis: { status: "available", relationship_drift: analysis.relationships },
    analysis_explanation: analysis,
    ...overrides.result,
  };
}

function renderWorkspace({ path = "/sites/current", result = analysisResult(), canonicalConnectorResult = null, apiFetch = vi.fn(), onWorkspaceNavigate = vi.fn(), onWorkspaceChange = vi.fn(), workspaceSession = null, currentWorkspace = null, role = "operator" } = {}) {
  window.history.replaceState({}, "", path);
  const props = {
    liveOps: {},
    canonicalFinding: { exists: false },
    currentSession: {},
    effectiveLatestUploadResult: result,
    effectiveLatestUploadSnapshot: result ? { status: "complete", sii_completed: true } : {},
    canonicalConnectorResult,
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

  it.each(["findings", "investigations", "evidence"])("never falls back to a default finding for an unknown %s deep link", async (routeName) => {
    const apiFetch = vi.fn(async () => ({ ok: true, json: async () => ({ runs: [] }) }));
    renderWorkspace({ path: `/${routeName}/workspace-b-secret`, apiFetch });
    const heading = routeName === "findings" ? "Finding unavailable" : routeName === "investigations" ? "Investigation unavailable" : "Evidence record unavailable";
    expect(await screen.findByRole("heading", { name: heading })).toBeTruthy();
    expect(screen.getAllByText(/unavailable/i).length).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { name: "Chiller 03 changed" })).toBeNull();
    expect(document.body.textContent).not.toContain("workspace-b-secret");
  });

  it("starts an empty production workspace at Data Connections", () => {
    const { onWorkspaceNavigate } = renderWorkspace({ result: null });
    expect(screen.getByTestId("workspace-state-noDataset")).toBeTruthy();
    expect(screen.getByText(/Operations Brief · Setup needed/)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Connect a data source" })).toBeTruthy();
    expect(screen.getByText(/map them into a defined physical system/i)).toBeTruthy();
    expect(screen.queryByText(/historical dataset/i)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Add data source" }));
    expect(onWorkspaceNavigate).toHaveBeenCalledWith("data-connections");
  });

  it("does not activate completed evidence history when an ordinary workspace route hydrates", async () => {
    let releaseHistory;
    const historyResponse = new Promise((resolve) => { releaseHistory = resolve; });
    const oldRun = {
      run_id: "old-run",
      adaptive_site_key: "site::default",
      site_name: "Old Plant",
      status: "completed",
      observation_status: "open",
      rows_received: 100,
      rows_accepted: 100,
      evidence_summary: ["Old persisted operating evidence."],
      condition: {
        object_type: "condition",
        condition_id: "old-condition",
        headline: "Old persisted analysis",
        confidence: "high",
        affected_signals: ["Pump power", "Flow"],
        localization: { system: "Pumping System" },
        supporting_evidence: ["Old persisted operating evidence."],
      },
    };
    const apiFetch = vi.fn((path) => {
      if (path === "/api/evidence/runs?limit=100") return historyResponse;
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    renderWorkspace({ path: "/sites/site%3A%3Adefault", result: null, apiFetch });
    expect(screen.getByTestId("workspace-state-noDataset")).toBeTruthy();
    expect(screen.queryByTestId("operations-brief")).toBeNull();

    await act(async () => {
      releaseHistory({ ok: true, json: async () => ({ runs: [oldRun] }) });
      await historyResponse;
    });

    await waitFor(() => expect(screen.getByTestId("workspace-state-noDataset")).toBeTruthy());
    expect(screen.queryByTestId("operations-brief")).toBeNull();
    expect(document.body.textContent).not.toContain("Old persisted analysis");
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
    expect(screen.getByRole("heading", { name: "Analysis complete" })).toBeTruthy();
    expect(screen.getByText("1 finding deserves review.")).toBeTruthy();
    expect(screen.getByText("Findings for review").closest("div").textContent).toContain("1");
    expect(screen.getByText("Systems represented").closest("div").textContent).toContain("1");
    expect(screen.getByRole("heading", { name: "What to review" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Monitoring" })).toBeNull();
    expect(screen.queryByText("Technical details")).toBeNull();
  });

  it("keeps the alert scannable and progressively discloses evidence", () => {
    renderWorkspace();
    const card = screen.getByTestId("compact-finding-card");
    const finding = within(card);
    expect(finding.getByText("Cooling system")).toBeTruthy();
    expect(finding.getByRole("heading", { name: "Condenser-side behavior changed" })).toBeTruthy();
    expect(finding.getByText("System / asset")).toBeTruthy();
    for (const label of ["Finding", "Change confidence", "Important limitation"]) expect(finding.getByText(label)).toBeTruthy();
    expect(finding.queryByText("Requested next action")).toBeNull();
    expect(finding.queryByText("Evidence and limitations")).toBeNull();
    expect(finding.queryByText("Condenser approach temperature increased 15.3%.")).toBeNull();
    expect(finding.queryByText("Compressor current increased 5.5%.")).toBeNull();
    expect(finding.getByRole("button", { name: "Review finding" })).toBeTruthy();
    expect(within(card).getAllByRole("button")).toHaveLength(1);
    expect(card.querySelector("details")).toBeNull();
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
    expect(view.getByRole("heading", { name: "Pumping System relationship decreased" })).toBeTruthy();
    expect(view.getByText("Pumping System")).toBeTruthy();
    expect(card.querySelector(".operational-finding__evidence")).toBeNull();
    expect(view.queryByText("3 relationship changes align through flow and discharge pressure.")).toBeNull();
    expect(view.getByRole("button", { name: "Review finding" })).toBeTruthy();

    fireEvent.click(view.getByRole("button", { name: "Review finding" }));
    expect(window.location.pathname).toBe("/findings/condition-pump");
    expect(screen.getByText("Comparable operating evidence supports the condition.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open investigation" }));
    expect(screen.getByRole("heading", { name: "Persistence and confidence" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Operating context" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Timeline" })).toBeTruthy();
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

    expect(screen.getByRole("heading", { name: "Cooling Distribution relationship decreased" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Review finding" }));

    expect(screen.getAllByText("Not established").length).toBeGreaterThan(0);
    expect(screen.getByText("Operating conditions differed from baseline.")).toBeTruthy();
    expect(screen.queryByText(/^Trajectory$/)).toBeNull();
    expect(screen.queryByText(/Observed for 81 days/i)).toBeNull();
    expect(screen.getAllByText("Return temperature signal / Power signal changed from strong to weak coupling.").length).toBeGreaterThan(0);
    expect(document.querySelectorAll(".case-sections--review > section:last-child li")).toHaveLength(3);
    expect(screen.queryByText("This fourth action must not appear.")).toBeNull();
    const headings = [...document.querySelectorAll(".case-sections--review > section > h2")].map((node) => node.textContent);
    expect(headings).toEqual(["What changed", "Why this deserves attention", "Evidence assessment", "Important limitation", "Where to investigate next"]);
    for (const paragraph of document.querySelectorAll(".case-sections--review p")) {
      expect(paragraph.textContent.length).toBeLessThanOrEqual(260);
    }
  });

  it("keeps workflow mutation out of analytical Results and Finding Review", () => {
    renderWorkspace();
    expect(screen.queryByRole("button", { name: "I’m checking this" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Review finding" }));
    expect(screen.queryByRole("button", { name: "I’m checking this" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Known or explained" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Not useful" })).toBeNull();
    expect(screen.getByRole("button", { name: "Open investigation" })).toBeTruthy();
  });

  it("orders finding review around change, importance, checks, timeline, and evidence", () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Review finding" }));
    expect(window.location.pathname).toBe("/findings/finding-1");
    const headings = [...document.querySelectorAll(".case-sections--review > section > h2")].map((node) => node.textContent);
    expect(headings).toEqual(["What changed", "Why this deserves attention", "Evidence assessment", "Important limitation", "Where to investigate next"]);
    expect(screen.queryByText("Cause / attribution")).toBeNull();
    for (const dimension of ["Change confidence", "Evidence quality", "Persistence", "Operating context", "Corroboration", "Evidence sufficiency"]) {
      expect(screen.getAllByText(dimension).length).toBeGreaterThan(0);
    }
    expect(screen.queryByText("Cause established?")).toBeNull();
    expect(screen.getByRole("button", { name: "Open investigation" })).toBeTruthy();
  });

  it("opens a progressive investigation without evidence-record audit internals", () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Review finding" }));
    fireEvent.click(screen.getByRole("button", { name: "Open investigation" }));
    expect(window.location.pathname).toBe("/investigations/finding-1");
    const headings = [...document.querySelectorAll(".case-sections--investigation > section > h2")].map((node) => node.textContent);
    expect(headings).toEqual(["Primary relationship comparison", "Relationship evidence", "Persistence and confidence", "Operating context", "System evidence channels", "Data quality and comparability", "Timeline", "Source signals and lineage"]);
    for (const label of ["Audit history", "Engine and build", "Classification", "Evidence sufficiency"]) expect(screen.queryByRole("heading", { name: label })).toBeNull();
  });

  it("moves directly from finding to investigation to the evidence record", () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Review finding" }));
    fireEvent.click(screen.getByRole("button", { name: "Open investigation" }));
    fireEvent.click(screen.getByRole("button", { name: "Open evidence record" }));
    expect(window.location.pathname).toBe("/evidence/finding-1");
    expect(screen.getByTestId("evidence-record")).toBeTruthy();
    for (const heading of ["Record identity", "Finding-owned relationships", "Finding provenance and lineage", "Evidence sufficiency", "Audit history"]) expect(screen.getAllByRole("heading", { name: heading }).length).toBeGreaterThan(0);
    expect(document.body.textContent).toContain("pearson_correlation");
    expect(document.body.textContent).toContain("0.094013");
    expect(document.body.textContent).toContain("0.833811");
    expect(document.body.textContent).toContain("0.739798");
  });

  it("supports direct workflow navigation and keyboard search", () => {
    renderWorkspace();
    const navigation = screen.getByRole("navigation", { name: "Primary navigation" });
    for (const label of ["System Status", "Systems", "Analysis Findings", "Evidence & Outcomes", "Data"]) expect(within(navigation).getByRole("button", { name: label })).toBeTruthy();
    expect(within(navigation).queryByRole("button", { name: "Live Monitoring" })).toBeNull();
    fireEvent.click(within(navigation).getByRole("button", { name: "Evidence & Outcomes" }));
    expect(window.location.pathname).toBe("/investigations");
    fireEvent.click(within(navigation).getByRole("button", { name: "Systems" }));
    expect(screen.getByRole("heading", { name: "North Plant" })).toBeTruthy();
    const search = screen.getByRole("combobox", { name: /Search sites/i });
    fireEvent.change(search, { target: { value: "Cooling system" } });
    fireEvent.keyDown(search, { key: "Enter" });
    expect(window.location.pathname).toBe("/systems/Cooling%20system");
    expect(screen.getByText("Cooling system")).toBeTruthy();
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
    expect(screen.getByRole("heading", { name: "Relationship evidence" })).toBeTruthy();
  });

  it("speaks confidently when the completed analysis has no meaningful changes", () => {
    const result = analysisResult({ analysis: { insights: [] }, result: { data_gaps: [], data_quality: { coverage_percent: 100, warnings: [] } } });
    renderWorkspace({ result });
    expect(screen.getAllByText("No supported material behavioral change.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("The available comparison remains within the learned system-behavior boundary.").length).toBeGreaterThan(0);
    expect(screen.queryByText("Evidence insufficient")).toBeNull();
  });

  it("routes a stable connector result through result-scoped investigation and evidence without a fake finding", () => {
    const resultId = "77777777-7777-4777-8777-777777777777";
    const connectorResult = {
      result_id: resultId,
      analysis_window_id: "88888888-8888-4888-8888-888888888888",
      connection_id: "11111111-1111-4111-8111-111111111111",
      source_run_id: "44444444-4444-4444-8444-444444444444",
      facility_id: "facility-a",
      facility_name: "North Plant",
      system_id: "cooling",
      asset_id: "chiller-03",
      window_start: "2026-08-25T00:00:00Z",
      window_end: "2026-08-26T00:00:00Z",
      payload_digest: "a".repeat(64),
      artifact_schema_version: "telemetry-canonical-result-artifact.v1",
      execution_contract_version: "analysis-window-execution.v1",
      analysis_schema_version: "analysis-result-v1",
      analysis_contract_version: "analysis-result-v1",
      lineage_verified: true,
      sii_completed: true,
      sii_reliable_enough_to_show: true,
      evidence_persisted: true,
      baseline_sufficient: true,
      data_quality: { coverage_percent: 100, warnings: [] },
      analysis_result: {
        schema_version: "analysis-result-v1",
        systems: [{ id: "cooling", name: "Cooling system" }],
        relationships: [{ id: "rel-1", columns: ["temp", "power"], baseline_strength: 0.8, current_strength: 0.81, change_type: "stable" }],
        conditions: [],
        insights: [],
      },
      sii_result: { temporal_analysis: { status: "stable" }, data_conditions: { status: "sufficient" }, engine: { name: "sii", version: "1" } },
    };
    renderWorkspace({ result: null, canonicalConnectorResult: connectorResult });

    expect(screen.getByRole("heading", { name: "No supported material behavioral change." })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Review finding" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open investigation" }));
    expect(window.location.pathname).toBe(`/investigations/${resultId}`);
    expect(screen.getByTestId("investigation-workspace")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open evidence record" }));
    expect(window.location.pathname).toBe(`/evidence/${resultId}`);
    expect(screen.getByTestId("evidence-record")).toBeTruthy();
    expect(screen.getByText(resultId)).toBeTruthy();
    expect(screen.getAllByText("telemetry-canonical-result-artifact.v1").length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toContain("finding-" + resultId);
  });

  it("keeps material connector finding and canonical result lineage identical through every disclosure depth", () => {
    const base = analysisResult();
    const resultId = "77777777-7777-4777-8777-777777777778";
    const digest = "c".repeat(64);
    const connectorResult = {
      ...base,
      result_id: resultId,
      analysis_window_id: "88888888-8888-4888-8888-888888888889",
      connection_id: "11111111-1111-4111-8111-111111111111",
      source_run_id: "44444444-4444-4444-8444-444444444444",
      facility_id: "facility-a",
      system_id: "cooling",
      asset_id: "chiller-03",
      payload_digest: digest,
      artifact_schema_version: "telemetry-canonical-result-artifact.v1",
      execution_contract_version: "analysis-window-execution.v1",
      analysis_schema_version: "analysis-result-v1",
      analysis_contract_version: "analysis-result-v1",
      lineage_verified: true,
      analysis_result: base.analysis_explanation,
      canonical_result: {
        identity: {
          result_id: resultId,
          analysis_id: "analysis-connector-1",
          analysis_window_id: "88888888-8888-4888-8888-888888888889",
          source_ingestion_run_id: "44444444-4444-4444-8444-444444444444",
          payload_digest: digest,
          observation_count: 20,
          observation_lineage_digest: "d".repeat(64),
          artifact_schema_version: "telemetry-canonical-result-artifact.v1",
          execution_contract_version: "analysis-window-execution.v1",
          analysis_contract_version: "analysis-result-v1",
        },
        reference_metadata: {},
        finding_ids: { items: ["finding-1"], total: 1, truncated: false },
        evidence_ids: { items: ["ev-finding-1"], total: 1, truncated: false },
        evidence_audit: { identity: { result_id: resultId }, finding_record_count: 1 },
      },
    };
    renderWorkspace({ result: null, canonicalConnectorResult: connectorResult });

    fireEvent.click(screen.getByRole("button", { name: "Review finding" }));
    expect(window.location.pathname).toBe("/findings/finding-1");
    expect(screen.getByTestId("finding-review")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open investigation" }));
    expect(window.location.pathname).toBe("/investigations/finding-1");
    expect(screen.getByTestId("investigation-workspace")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open evidence record" }));
    expect(window.location.pathname).toBe("/evidence/finding-1");
    expect(screen.getByTestId("evidence-record")).toBeTruthy();
    expect(screen.getAllByText("finding-1").length).toBeGreaterThan(0);
    expect(screen.getAllByText(resultId).length).toBeGreaterThan(0);
    expect(screen.getAllByText(digest).length).toBeGreaterThan(0);
  });

  it("keeps a zero-finding insufficient connector result retrievable without creating a review case", () => {
    const resultId = "99999999-9999-4999-8999-999999999999";
    const connectorResult = {
      result_id: resultId,
      facility_name: "North Plant",
      system_id: "cooling",
      payload_digest: "b".repeat(64),
      lineage_verified: true,
      sii_completed: true,
      sii_reliable_enough_to_show: true,
      evidence_persisted: true,
      baseline_sufficient: false,
      data_quality: { coverage_percent: 40, warnings: ["Comparable baseline coverage is insufficient."] },
      analysis_result: { schema_version: "analysis-result-v1", systems: [{ id: "cooling", name: "Cooling system" }], conditions: [], insights: [], warnings: ["Comparable baseline coverage is insufficient."] },
      sii_result: { data_conditions: { status: "insufficient" } },
    };
    renderWorkspace({ result: null, canonicalConnectorResult: connectorResult });

    expect(screen.getByRole("heading", { name: "Insufficient evidence" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Review finding" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open investigation" }));
    expect(screen.getByTestId("investigation-workspace")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open evidence record" }));
    expect(screen.getByTestId("evidence-record")).toBeTruthy();
    expect(screen.getAllByText(/Comparable baseline coverage is insufficient/).length).toBeGreaterThan(0);
  });

  it("keeps resolved findings out of every triage list without claiming the system is stable", () => {
    window.localStorage.setItem("neraium.operations-brief.review-state.engineer@neraium.test-anonymous", JSON.stringify({
      "finding-1": { state: "resolved" },
    }));
    renderWorkspace();
    expect(screen.getByRole("heading", { name: "Analysis complete" })).toBeTruthy();
    expect(screen.getByText("No findings currently deserve review from this completed analysis.")).toBeTruthy();
    expect(screen.queryByTestId("compact-finding-card")).toBeNull();
    expect(screen.queryByText("No supported material behavioral change.")).toBeNull();

    const navigation = screen.getByRole("navigation", { name: "Primary navigation" });
    fireEvent.click(within(navigation).getByRole("button", { name: "Analysis Findings" }));
    expect(screen.getByText("No findings currently deserve review from this completed analysis.")).toBeTruthy();
    fireEvent.click(within(navigation).getByRole("button", { name: "Evidence & Outcomes" }));
    expect(screen.getByText("No findings currently deserve review from this completed analysis.")).toBeTruthy();
    fireEvent.click(within(navigation).getByRole("button", { name: "Systems" }));
    expect(screen.getAllByText("0 for review").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /Cooling system/i }));
    expect(screen.getByText("No findings currently deserve review for Cooling system.")).toBeTruthy();
    expect(screen.queryByText("No supported material behavioral change.")).toBeNull();
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
