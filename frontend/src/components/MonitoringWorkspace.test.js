/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import MonitoringWorkspace from "./MonitoringWorkspace";

vi.mock("./DataConnectionsWorkspace", () => ({
  default: () => React.createElement("div", { "data-testid": "data-import" }, "Historical import controls"),
}));

const relationship = {
  id: "pump-flow",
  columns: ["pump_power_kw", "flow_gpm"],
  change_type: "changed",
  baseline_strength: 0.84,
  current_strength: 0.31,
  correlation_delta: -0.53,
  source_time_ranges: [{
    baseline_start: "2026-07-01T00:00:00Z",
    baseline_end: "2026-07-10T00:00:00Z",
    current_start: "2026-07-24T02:10:00Z",
    current_end: "2026-07-25T02:10:00Z",
    condition_group: "Comparable load periods",
  }],
};

function resultWithFindings(count = 1, overrides = {}) {
  const insights = Array.from({ length: count }, (_, index) => ({
    id: `finding-${index + 1}`,
    title: index ? "Flow and pressure behavior changed" : "Pump response changed",
    system: index ? "Distribution" : "Pumping",
    confidence: "high",
    what_changed: "The learned relationship moved outside its usual pattern.",
    variables: index ? ["flow_gpm", "main_pressure_psi"] : ["pump_power_kw", "flow_gpm", "pump_speed_pct"],
    supporting_evidence: ["The relationship changed across repeated comparison windows.", "Three signals changed together."],
    contributing_relationships: [index ? { ...relationship, id: "flow-pressure", columns: ["flow_gpm", "main_pressure_psi"] } : relationship],
  }));
  return {
    job_id: "current-run",
    facility_name: "North Plant",
    filename: "north-plant.csv",
    status: "complete",
    completed_at: "2026-07-25T02:10:00Z",
    deformation_started_at: "2026-07-24T02:10:00Z",
    sii_completed: true,
    sii_reliable_enough_to_show: true,
    data_quality: { coverage_percent: 96, warnings: [] },
    baseline_analysis: { status: "available", relationship_drift: [relationship] },
    analysis_explanation: {
      systems: [{ id: "pumping", name: "Pumping" }, { id: "distribution", name: "Distribution" }],
      relationships: [relationship],
      insights,
    },
    ...overrides,
  };
}

function quietResult(overrides = {}) {
  const base = resultWithFindings(0);
  return { ...base, ...overrides, analysis_explanation: { ...base.analysis_explanation, insights: [], ...(overrides.analysis_explanation || {}) } };
}

function apiWith({ runs = [], connections = [] } = {}) {
  return vi.fn(async (path) => ({
    ok: true,
    json: async () => path.startsWith("/api/evidence") ? { runs } : { connections },
  }));
}

function renderWorkspace({
  path = "/status",
  activeWorkspace,
  result = quietResult(),
  runs = [],
  connections = [],
  liveOps = {},
  gateProcessing = null,
} = {}) {
  window.history.replaceState({}, "", path);
  const route = activeWorkspace ?? (path.startsWith("/findings/") ? "evidence" : path.slice(1) || "status");
  const apiFetch = apiWith({ runs, connections });
  const props = {
    activeWorkspace: route,
    apiFetch,
    accessCode: "",
    liveOps: {
      systems: [{ id: "pumping", name: "Pumping" }],
      connectionTone: "online",
      dataFreshness: { label: "Live", tone: "live" },
      ...liveOps,
    },
    currentSession: {},
    canonicalFinding: { exists: false },
    gateProcessing,
    effectiveLatestUploadResult: result,
    effectiveLatestUploadSnapshot: result ? { status: result.status, sii_completed: result.sii_completed, last_processed_at: result.completed_at } : { status: "empty" },
    currentUser: { name: "Operator", email: "operator@neraium.test", role: "operator" },
    onWorkspaceNavigate: vi.fn(),
    onUploadComplete: vi.fn(),
  };
  return { ...render(React.createElement(MonitoringWorkspace, props)), props, apiFetch };
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.history.replaceState({}, "", "/");
});

describe("MonitoringWorkspace product states", () => {
  it("shows a calm quiet state without manufacturing activity", async () => {
    renderWorkspace();
    expect(screen.getByRole("heading", { name: "No meaningful relationship changes detected." })).toBeTruthy();
    expect(screen.getByText("Last successful analysis")).toBeTruthy();
    expect(screen.getByText("Learned relationships")).toBeTruthy();
    expect(screen.queryByText(/review queue/i)).toBeNull();
    expect(screen.queryByTestId("finding-card")).toBeNull();
  });

  it("shows one concise active relationship change", () => {
    renderWorkspace({ result: resultWithFindings(1) });
    expect(screen.getByText("Meaningful change detected")).toBeTruthy();
    const card = screen.getByTestId("finding-card");
    expect(within(card).getByRole("heading", { name: "Pump response changed" })).toBeTruthy();
    expect(within(card).getByText(/no longer responding/i)).toBeTruthy();
    expect(within(card).getByText("3 related signals")).toBeTruthy();
    expect(within(card).getByRole("button", { name: "View evidence" })).toBeTruthy();
    expect(card.textContent).not.toMatch(/inspect|possible cause|root cause|repair/i);
  });

  it("links to all active findings when more than one is present", async () => {
    renderWorkspace({ result: resultWithFindings(1), runs: [{
      run_id: "second-active-run",
      status: "complete",
      meaningful_change: true,
      observation_status: "open",
      system_id: "Distribution",
      variables: ["main_pressure_psi", "flow_gpm"],
      evidence_summary: ["Pressure and flow changed together."],
      deformation_started_at: "2026-07-23T00:00:00Z",
      completed_at: "2026-07-25T00:00:00Z",
    }] });
    expect(await screen.findByRole("button", { name: "View all 2 active findings" })).toBeTruthy();
  });

  it("keeps resolved backend findings in history without making them active", async () => {
    const run = {
      run_id: "resolved-run",
      status: "complete",
      observation_type: "relationship_drift",
      observation_status: "resolved",
      structural_state: "Change detected",
      system_id: "Pumping",
      variables: ["pump_power_kw", "flow_gpm"],
      evidence_summary: ["The relationship changed across repeated windows."],
      deformation_started_at: "2026-07-20T00:00:00Z",
      completed_at: "2026-07-21T00:00:00Z",
    };
    renderWorkspace({ path: "/findings", activeWorkspace: "findings", runs: [run] });
    fireEvent.change(screen.getByLabelText("State"), { target: { value: "resolved" } });
    const card = await screen.findByTestId("finding-card");
    expect(within(card).getByText("resolved")).toBeTruthy();
  });

  it("opens evidence with comparison, timeline, persistence, and collapsed measurements", () => {
    renderWorkspace({ result: resultWithFindings(1) });
    fireEvent.click(screen.getByRole("button", { name: "View evidence" }));
    expect(screen.getByTestId("evidence-page")).toBeTruthy();
    expect(screen.getByText("What relationship changed")).toBeTruthy();
    expect(screen.getByText("Baseline versus current relationship")).toBeTruthy();
    expect(screen.getByText("When the change began")).toBeTruthy();
    const details = screen.getByText("Detailed measurements").closest("details");
    expect(details.open).toBe(false);
    fireEvent.click(screen.getByText("Detailed measurements"));
    expect(within(details).getByText("0.8400")).toBeTruthy();
  });

  it("shows restrained comparable-context and sensor-quality limitations", async () => {
    const run = {
      run_id: "limited-run",
      status: "complete",
      meaningful_change: true,
      observation_status: "open",
      system_id: "Distribution",
      variables: ["flow_gpm", "main_pressure_psi"],
      evidence_summary: ["Pressure and flow changed together."],
      warnings: ["Comparable operating context was limited by sparse samples.", "Sensor showed an abrupt step change."],
      deformation_started_at: "2026-07-24T00:00:00Z",
      completed_at: "2026-07-25T00:00:00Z",
    };
    renderWorkspace({ path: "/findings/limited-run", activeWorkspace: "evidence", runs: [run] });
    expect(await screen.findByText("Comparable operating data was limited.")).toBeTruthy();
    expect(screen.getByText("One sensor showed an abrupt step.")).toBeTruthy();
  });

  it("surfaces stale data as a restrained monitoring notice", () => {
    renderWorkspace({ liveOps: { dataFreshness: { label: "Stale", tone: "stale" } } });
    expect(screen.getByText("Data is stale")).toBeTruthy();
  });

  it("keeps existing state visible when the latest analysis failed", () => {
    renderWorkspace({ result: quietResult({ status: "failed" }) });
    expect(screen.getByText("Analysis failed")).toBeTruthy();
    expect(screen.getByText("No meaningful relationship changes detected.")).toBeTruthy();
  });

  it("shows a disconnected live source on Data", async () => {
    renderWorkspace({
      path: "/data",
      activeWorkspace: "data",
      connections: [{ connection_id: "bas", name: "Building BAS", source_type: "external_rest_api", status: "offline", error_message: "Connection timed out", sensors_detected: 0 }],
    });
    expect(await screen.findByText("Building BAS")).toBeTruthy();
    expect(screen.getAllByText("Disconnected").length).toBeGreaterThan(0);
    expect(screen.getByText("Connection timed out")).toBeTruthy();
  });

  it("shows baseline learning and transitions the conceptual flow toward monitoring", () => {
    renderWorkspace({ result: { job_id: "learning", status: "processing", processing_state: "baseline_modeling" }, gateProcessing: { active: true, status: "processing" } });
    expect(screen.getByRole("heading", { name: "Learning how signals normally behave together." })).toBeTruthy();
    expect(screen.getByText("Monitoring begins when baseline learning is complete.")).toBeTruthy();
  });

  it("supports direct evidence URLs and old stored field names", async () => {
    const legacyRun = {
      run_id: "legacy-run",
      status: "complete",
      observation_type: "trajectory_drift",
      observation_status: "open",
      structural_state: "High",
      system_id: "Pumping",
      variables: ["pump_power_kw", "flow_gpm"],
      evidence_summary: ["The relationship changed from its baseline."],
      historical_fact: "Historical comparison evidence supports a change.",
      deformation_started_at: "2026-07-20T00:00:00Z",
      completed_at: "2026-07-21T00:00:00Z",
      drift_metrics: { baseline_distance: 0.61 },
    };
    renderWorkspace({ path: "/findings/legacy-run", activeWorkspace: "evidence", runs: [legacyRun] });
    expect(await screen.findByTestId("evidence-page")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Pump response changed" })).toBeTruthy();
  });

  it("persists optional acknowledgment across refresh without changing analysis", () => {
    const first = renderWorkspace({ result: resultWithFindings(1) });
    fireEvent.click(screen.getByRole("button", { name: "Acknowledge" }));
    expect(screen.getByRole("button", { name: "Acknowledged" }).getAttribute("aria-pressed")).toBe("true");
    first.unmount();
    renderWorkspace({ result: resultWithFindings(1) });
    expect(screen.getByRole("button", { name: "Acknowledged" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("provides a mobile navigation control without motion-dependent access", () => {
    renderWorkspace();
    const menu = screen.getByRole("button", { name: "Open menu" });
    fireEvent.click(menu);
    expect(screen.getByRole("button", { name: "Close menu" }).getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeTruthy();
  });
});
