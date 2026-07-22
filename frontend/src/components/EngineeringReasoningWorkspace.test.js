/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import EngineeringReasoningWorkspace from "./EngineeringReasoningWorkspace";

const result = {
  facility_name: "North Plant", job_id: "run-42", processed_at: "2026-07-22T08:00:00Z",
  data_quality: { coverage_percent: 82, warnings: ["Historian X was unavailable from 01:10 to 03:05."] },
  data_gaps: [{ id: "gap-1", source: "Historian X", duration: "1h 55m", signals: ["Flow-01"], overlaps_change_window: true }],
  replay_timeline: { timeline: [{ timestamp: "2026-07-21T08:00:00Z" }, { timestamp: "2026-07-22T08:00:00Z" }] },
  analysis_explanation: {
    systems: [{ id: "flow", name: "Flow & Pressure" }],
    relationships: [{ id: "rel-1", columns: ["Chiller-03", "Flow-01"], change_type: "weakened", baseline_strength: 0.81, current_strength: 0.42, confidence: "qualified" }],
    insights: [{ id: "finding-1", title: "Flow response changed", system: "Flow & Pressure", confidence: "high", what_changed: "Flow response weakened under comparable demand.", why_it_matters: "The mapped subsystem response is less stable than the learned comparison.", recommended_check: "Review the Chiller-03 and Flow-01 trend overlay.", variables: ["Chiller-03", "Flow-01"], supporting_evidence: ["Flow response weakened in the current window.", "The mapped relationship moved below its learned range."], confirmation_criteria: "A comparable operating window should reproduce or rule out the relationship shift.", contributing_relationships: [{ id: "rel-1", columns: ["Chiller-03", "Flow-01"], change_type: "weakened", baseline_strength: 0.81, current_strength: 0.42 }] }],
  },
  governance_boundary: { statement: "Raw telemetry remains at this site.", status: "Applied" },
};

function renderWorkspace(path = "/portfolio") {
  window.history.replaceState({}, "", path);
  return render(React.createElement(EngineeringReasoningWorkspace, { liveOps: {}, canonicalFinding: { exists: false }, currentSession: {}, effectiveLatestUploadResult: result, effectiveLatestUploadSnapshot: { status: "complete" }, apiFetch: vi.fn(), onWorkspaceNavigate: vi.fn(), currentUser: { name: "Engineer One", role: "operator" } }));
}

afterEach(() => { cleanup(); window.history.replaceState({}, "", "/"); });

describe("EngineeringReasoningWorkspace", () => {
  it("opens with portfolio evidence distribution and an accessible list alternative", () => {
    renderWorkspace();
    expect(screen.getByTestId("engineering-reasoning-platform")).toBeTruthy();
    expect(screen.getByRole("heading", { name: /Where does the evidence warrant attention/i })).toBeTruthy();
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getAllByText("North Plant").length).toBeGreaterThan(0);
    expect(screen.getByText("Raw telemetry remains at this site.")).toBeTruthy();
    expect(screen.queryByText(/100% confidence/i)).toBeNull();
  });

  it("supports site selection and one canonical highest-priority finding", () => {
    renderWorkspace();
    fireEvent.click(screen.getAllByRole("button", { name: "Open site" })[0]);
    expect(screen.getByRole("heading", { name: "North Plant" })).toBeTruthy();
    expect(screen.getByText(/Where should I spend the next hour/i)).toBeTruthy();
    expect(screen.getAllByText("Flow response changed")).toHaveLength(1);
    expect(screen.getByText("Observed change")).toBeTruthy();
    expect(screen.getByText("Why it matters")).toBeTruthy();
    expect(screen.getByText("Contradicting or limiting evidence")).toBeTruthy();
  });

  it("searches an asset tag and enters a relationship investigation", () => {
    renderWorkspace();
    const search = screen.getByRole("combobox", { name: /Search sites/i });
    fireEvent.change(search, { target: { value: "Chiller-03" } });
    fireEvent.click(screen.getByRole("button", { name: /Asset \/ signal: Chiller-03/i }));
    expect(screen.getByRole("heading", { name: "Behavioral constellation" })).toBeTruthy();
    expect(screen.getAllByText(/Read-only intelligence/).length).toBeGreaterThan(0);
    expect(screen.getByRole("slider", { name: /Relationship comparison time/i })).toBeTruthy();
    expect(screen.getByRole("dialog", { name: /Chiller-03/i })).toBeTruthy();
    expect(screen.getAllByText("Data Gap").length).toBeGreaterThan(0);
    expect(screen.getByText("View relationship table")).toBeTruthy();
  });

  it("updates relationship evidence when scrubbing to a frame without historical edge values", () => {
    renderWorkspace("/investigations/finding-1");
    const slider = screen.getByRole("slider", { name: /Relationship comparison time/i });
    fireEvent.change(slider, { target: { value: "24" } });
    expect(screen.getByText("24 hours before now")).toBeTruthy();
    expect(screen.getAllByText("Historical relationship evidence not supplied").length).toBeGreaterThan(0);
  });

  it("never renders control or alarm-management actions", () => {
    renderWorkspace("/investigations/finding-1");
    const text = document.body.textContent;
    for (const forbidden of ["Acknowledge", "Snooze", "Silence", "Reset", "Start equipment", "Stop equipment", "Setpoint"]) expect(text).not.toContain(forbidden);
    expect(screen.getAllByText(/No control actions/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Review CMMS payload" })).toBeTruthy();
  });
});
