/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import EngineeringReasoningWorkspace from "./EngineeringReasoningWorkspace";

const result = {
  facility_name: "North Plant",
  job_id: "run-42",
  data_quality: {
    coverage_percent: 82,
    warnings: [
      "Historian X was unavailable during the comparison window.",
      "3 dropped rows.",
      "One unmapped column.",
      "A constant sensor was excluded.",
    ],
  },
  data_gaps: [{ id: "gap-1", source: "Historian X", signals: ["Efficiency"], overlaps_change_window: true }],
  analysis_explanation: {
    fingerprint: { status: "Established" },
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
      why_it_matters: "Neraium found a repeatable difference from the learned operating pattern.",
      variables: ["Condenser approach temperature", "Compressor current"],
      supporting_evidence: [
        "Condenser approach temperature increased 15.3%.",
        "Compressor current increased 5.5%.",
        "The relationship moved outside its learned range.",
        "Relationship strength moved from 0.094013 to 0.833811.",
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
  },
};

function renderWorkspace(path = "/portfolio", overrides = {}) {
  window.history.replaceState({}, "", path);
  const props = {
    liveOps: {},
    canonicalFinding: { exists: false },
    currentSession: {},
    effectiveLatestUploadResult: result,
    effectiveLatestUploadSnapshot: { status: "complete" },
    apiFetch: vi.fn(),
    onWorkspaceNavigate: vi.fn(),
    currentUser: { name: "Engineer One", role: "operator" },
    ...overrides,
  };
  return render(React.createElement(EngineeringReasoningWorkspace, props));
}

afterEach(() => {
  cleanup();
  window.history.replaceState({}, "", "/");
});

describe("EngineeringReasoningWorkspace", () => {
  it("opens a one-site result directly with the operational answer in one card", () => {
    renderWorkspace();

    expect(screen.getByTestId("engineering-reasoning-platform")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "North Plant" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Sites" })).toBeNull();
    expect(screen.queryByText(/structural stability/i)).toBeNull();

    const card = document.querySelector('[data-finding-id="finding-1"]');
    expect(card).toBeTruthy();
    const answer = within(card.querySelector(".operational-finding__answer"));
    expect(answer.getByText("Change detected")).toBeTruthy();
    expect(answer.getByRole("heading", { name: "Condenser performance changed" })).toBeTruthy();
    expect(answer.getByText((text) => text.includes("North Plant") && text.includes("Chiller 03"))).toBeTruthy();
    expect(answer.getByText("Qualified")).toBeTruthy();
    expect(answer.getByRole("button", { name: "Open Evidence" })).toBeTruthy();

    const evidenceItems = card.querySelectorAll(".operational-finding__evidence li");
    expect(evidenceItems).toHaveLength(3);
    expect(card.textContent).not.toContain("0.094013");
    expect(screen.getAllByText("Condenser performance changed")).toHaveLength(1);
  });

  it("opens evidence directly and keeps exact calculations and trace controls in Technical Details", () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Open Evidence" }));

    expect(screen.getByText("What changed")).toBeTruthy();
    expect(screen.getByText("Supporting evidence")).toBeTruthy();
    expect(screen.getByText("Baseline vs current")).toBeTruthy();
    expect(screen.getByText("Why Neraium flagged it")).toBeTruthy();
    expect(screen.getAllByText("North Plant").length).toBeGreaterThan(0);
    expect(screen.getByText("Cooling system")).toBeTruthy();
    expect(screen.getByText("Condenser Water")).toBeTruthy();
    expect(screen.getByText("Chiller 03")).toBeTruthy();

    const primary = document.querySelector(".operational-evidence__sections");
    expect(primary.textContent).not.toContain("0.094013");
    expect(primary.textContent).not.toContain("0.833811");
    expect(primary.textContent).toContain("weak at baseline");
    expect(primary.textContent).toContain("strong now");

    const details = screen.getByText("Technical Details").closest("details");
    expect(details.open).toBe(false);
    fireEvent.click(screen.getByText("Technical Details"));
    expect(details.open).toBe(true);
    expect(within(details).getByText("0.094013")).toBeTruthy();
    expect(within(details).getByText("0.833811")).toBeTruthy();
    expect(within(details).getByRole("button", { name: "Open Trace Mode" })).toBeTruthy();
    expect(within(details).getByText("3 dropped rows.")).toBeTruthy();
  });

  it("shows only one short material limitation outside Technical Details", () => {
    renderWorkspace();
    const card = document.querySelector('[data-finding-id="finding-1"]');
    expect(card.querySelectorAll(".operational-finding__limitation")).toHaveLength(1);
    expect(card.textContent).not.toContain("3 dropped rows.");
    expect(card.textContent).not.toContain("One unmapped column.");
    expect(card.textContent).not.toContain("A constant sensor was excluded.");
  });

  it("uses Unassigned Analysis and Unassigned dataset when no site is mapped", () => {
    renderWorkspace("/portfolio", {
      effectiveLatestUploadResult: { ...result, facility_name: undefined, site_name: undefined },
    });

    expect(screen.getByRole("heading", { name: "Unassigned Analysis" })).toBeTruthy();
    expect(screen.getByText((text) => text.includes("Unassigned dataset") && text.includes("Chiller 03"))).toBeTruthy();
    expect(screen.queryByText("Current site")).toBeNull();
  });

  it("gives a system screen the same direct status, finding, location, and evidence action", () => {
    renderWorkspace();
    const search = screen.getByRole("combobox", { name: /Search sites/i });
    fireEvent.change(search, { target: { value: "Cooling system" } });
    fireEvent.click(screen.getByRole("button", { name: "System: Cooling system" }));

    expect(screen.getByRole("heading", { name: "Cooling system" })).toBeTruthy();
    expect(screen.getAllByText("Change detected").length).toBeGreaterThan(0);
    expect(screen.getByText("North Plant / Cooling system")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open Evidence" })).toBeTruthy();
  });

  it("shows a portfolio list only after more than one site is available", async () => {
    const apiFetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        runs: [{
          run_id: "site-b-run",
          adaptive_site_key: "site-b",
          site_name: "South Plant",
          system_name: "Pumping",
          rows_received: 10,
          rows_accepted: 10,
          evidence_summary: [],
          observation_status: "normal",
          baseline_status: "Established",
        }],
      }),
    }));
    renderWorkspace("/portfolio", { apiFetch });

    expect(await screen.findByRole("heading", { name: "Sites" })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Open Site" })).toHaveLength(2);
    fireEvent.click(screen.getAllByRole("button", { name: "Open Site" })[1]);
    expect(screen.getByRole("heading", { name: "South Plant" })).toBeTruthy();
    expect(window.location.pathname).toBe("/sites/site-b");
    expect(screen.queryByText(/evidence distribution|structural field|governance boundary/i)).toBeNull();
  });

  it("does not expose control actions or duplicate the finding workflow", () => {
    renderWorkspace();
    const text = document.body.textContent;
    for (const forbidden of ["Acknowledge", "Snooze", "Silence", "Reset", "Open investigation", "Highest-priority evidence"]) {
      expect(text).not.toContain(forbidden);
    }
    expect(screen.getAllByRole("button", { name: "Open Evidence" })).toHaveLength(1);
  });
});
