/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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
    }],
    ...overrides.analysis,
  };
  return {
    facility_name: "North Plant",
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

function renderWorkspace({ path = "/portfolio", result = analysisResult(), apiFetch = vi.fn(), onWorkspaceNavigate = vi.fn() } = {}) {
  window.history.replaceState({}, "", path);
  const props = {
    liveOps: {},
    canonicalFinding: { exists: false },
    currentSession: {},
    effectiveLatestUploadResult: result,
    effectiveLatestUploadSnapshot: result ? { status: "complete", sii_completed: true } : {},
    apiFetch,
    onWorkspaceNavigate,
    currentUser: { name: "Engineer One", email: "engineer@neraium.test", role: "operator" },
  };
  return { ...render(React.createElement(EngineeringReasoningWorkspace, props)), onWorkspaceNavigate };
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.history.replaceState({}, "", "/");
});

describe("EngineeringReasoningWorkspace shift workflow", () => {
  it("launches first-baseline onboarding instead of an analytical empty dashboard", () => {
    const { onWorkspaceNavigate } = renderWorkspace({ result: null });

    expect(screen.getByTestId("first-baseline-experience")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Create Your First Baseline" })).toBeTruthy();
    expect(screen.queryByText("Evidence insufficient")).toBeNull();
    expect(screen.getAllByText(/Import|Learn|Compare|Review/).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Import Historical Dataset" }));
    expect(onWorkspaceNavigate).toHaveBeenCalledWith("data-connections");
  });

  it("lets the operator exit onboarding into the baseline-needed workspace", () => {
    renderWorkspace({ result: null });
    fireEvent.click(screen.getByRole("button", { name: "Go to workspace" }));

    expect(screen.getByTestId("workspace-state-noDataset")).toBeTruthy();
    expect(screen.getByText("Baseline Needed")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "No baseline available" })).toBeTruthy();
    expect(screen.getByText("Import a historical dataset so Neraium can learn how your system normally behaves.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "View Supported Formats" }));
    expect(screen.getByRole("region", { name: "Supported historical dataset formats" })).toBeTruthy();
  });

  it("opens on a concise shift brief with the requested operational sections", () => {
    renderWorkspace();

    expect(screen.getByTestId("shift-brief")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "North Plant" })).toBeTruthy();
    for (const heading of ["New today", "Needs attention", "Monitoring", "Quiet systems"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
    }
    const summary = screen.getByRole("region", { name: "Morning summary" });
    for (const label of ["New findings", "Escalations", "Resolved", "Monitoring"]) {
      expect(within(summary).getByText(label)).toBeTruthy();
    }
    expect(screen.getByText("1 instrumentation issue remains under review.")).toBeTruthy();
  });

  it("caps a finding card at one evidence sentence, one next check, and three actions", () => {
    renderWorkspace();
    const card = document.querySelector(".operational-finding");
    const finding = within(card);

    expect(finding.getByText("Condenser Water")).toBeTruthy();
    expect(finding.getByRole("heading", { name: "Condenser-side behavior changed" })).toBeTruthy();
    expect(finding.getByText("Behavior change")).toBeTruthy();
    expect(finding.getByText("Narrowed")).toBeTruthy();
    expect(finding.getByText("New")).toBeTruthy();
    expect(finding.getByText("Condenser approach temperature increased 15.3%.")).toBeTruthy();
    expect(finding.getByText("Verify pressure transmitter.")).toBeTruthy();
    expect(card.querySelectorAll(".operational-finding__brief p")).toHaveLength(2);
    expect(card.textContent).not.toContain("Compressor current increased 5.5%.");
    for (const action of ["Review", "Acknowledge", "Evidence"]) {
      expect(finding.getByRole("button", { name: action })).toBeTruthy();
    }
  });

  it("acknowledges a finding without changing its evidence classification", () => {
    renderWorkspace();
    const card = document.querySelector(".operational-finding");
    const action = within(card).getByRole("button", { name: "Acknowledge" });
    fireEvent.click(action);

    const acknowledgedCard = document.querySelector(".operational-finding");
    expect(within(acknowledgedCard).getByText("Behavior change")).toBeTruthy();
    expect(within(acknowledgedCard).getByRole("button", { name: "Acknowledged" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("keeps why and how one click deeper with technical values collapsed", () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Review" }));

    expect(screen.getByText("What changed")).toBeTruthy();
    expect(screen.getByText("Why Neraium flagged it")).toBeTruthy();
    const details = screen.getByText("Technical Details").closest("details");
    expect(details.open).toBe(false);
    expect(document.querySelector(".operational-evidence__sections").textContent).not.toContain("0.094013");
    fireEvent.click(screen.getByText("Technical Details"));
    expect(within(details).getByText("0.094013")).toBeTruthy();
    expect(within(details).getByRole("button", { name: "Open Trace Mode" })).toBeTruthy();
  });

  it("speaks confidently when the completed analysis has no meaningful changes", () => {
    const result = analysisResult({
      analysis: { insights: [] },
      result: { data_gaps: [], data_quality: { coverage_percent: 100, warnings: [] } },
    });
    renderWorkspace({ result });

    expect(screen.getByText("No new unexplained system changes.")).toBeTruthy();
    expect(screen.getAllByText("Instrumentation is reporting normally.").length).toBeGreaterThan(0);
    expect(screen.queryByText("Evidence insufficient")).toBeNull();
  });

  it("shows the portfolio only when more than one site is available", async () => {
    const apiFetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ runs: [{
        run_id: "site-b-run",
        adaptive_site_key: "site-b",
        site_name: "South Plant",
        system_name: "Pumping",
        rows_received: 10,
        rows_accepted: 10,
        evidence_summary: [],
        observation_status: "normal",
        baseline_status: "Established",
      }] }),
    }));
    renderWorkspace({ apiFetch });

    expect(await screen.findByRole("heading", { name: "Sites" })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Open Site" })).toHaveLength(2);
  });
});
