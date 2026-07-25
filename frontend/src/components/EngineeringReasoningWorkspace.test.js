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
    warnings: ["Historian X was unavailable during the comparison window.", "3 dropped rows.", "One unmapped column."],
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
  return render(React.createElement(EngineeringReasoningWorkspace, {
    liveOps: {},
    canonicalFinding: { exists: false },
    currentSession: {},
    effectiveLatestUploadResult: result,
    effectiveLatestUploadSnapshot: { status: "complete" },
    apiFetch: vi.fn(),
    onWorkspaceNavigate: vi.fn(),
    currentUser: { name: "Engineer One", role: "operator" },
    ...overrides,
  }));
}

afterEach(() => {
  cleanup();
  window.history.replaceState({}, "", "/");
});

describe("EngineeringReasoningWorkspace progressive disclosure", () => {
  it("shows one compact finding card with no report prose", () => {
    renderWorkspace();

    const card = document.querySelector('[data-finding-id="finding-1"]');
    expect(card).toBeTruthy();
    expect(within(card).getByRole("heading", { name: "Condenser-side behavior changed" })).toBeTruthy();
    expect(within(card).getByText("Chiller 03")).toBeTruthy();
    expect(card.querySelectorAll(".operational-finding__evidence-line")).toHaveLength(1);
    expect(card.querySelectorAll(".operational-finding__next p")).toHaveLength(1);
    expect(within(card).getByRole("button", { name: "Review" })).toBeTruthy();
    expect(within(card).getByRole("button", { name: "Acknowledge" })).toBeTruthy();
    expect(within(card).getByRole("button", { name: "View evidence" })).toBeTruthy();
    expect(card.textContent).not.toContain("0.094013");
    expect(card.textContent).not.toContain("Historian X");
  });

  it("opens evidence in the five-part investigation order", () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Review" }));

    const headings = [...document.querySelectorAll(".operational-evidence__sections--classification .evidence-section > h2")].map((node) => node.textContent);
    expect(headings).toEqual([
      "What changed",
      "Why it matters",
      "Highest-value next checks",
      "Relationship timeline",
      "Supporting evidence",
    ]);
    expect(screen.getByText("Why Neraium classified it this way").closest("details").open).toBe(false);
    expect(screen.getByText("Operating-mode comparison details").closest("details").open).toBe(false);
    expect(screen.getByText("Sensor-health details").closest("details").open).toBe(false);
  });

  it("keeps exact calculations, limitations, lineage, and trace controls in deep detail", () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "View evidence" }));

    const limitations = screen.getByText("Data limitations").closest("details");
    expect(limitations.open).toBe(false);
    expect(limitations.textContent).toContain("Missing telemetry limits the conclusion.");

    const technical = screen.getByText("Technical analysis details").closest("details");
    expect(technical.open).toBe(false);
    fireEvent.click(technical.querySelector("summary"));
    expect(technical.open).toBe(true);
    expect(within(technical).getByText("0.094013")).toBeTruthy();
    expect(within(technical).getByText("0.833811")).toBeTruthy();
    expect(within(technical).getByText("3 dropped rows.")).toBeTruthy();
    expect(within(technical).getByRole("button", { name: "Open trace mode" })).toBeTruthy();
    expect(technical.textContent).toMatch(/lineage|source/i);
  });

  it("acknowledges a finding without removing its evidence action", () => {
    renderWorkspace();
    const acknowledge = screen.getByRole("button", { name: "Acknowledge" });
    acknowledge.focus();
    expect(document.activeElement).toBe(acknowledge);
    fireEvent.click(acknowledge);
    expect(screen.getByRole("button", { name: "Acknowledged" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "View evidence" })).toBeTruthy();
  });

  it("uses conservative legacy classification and keeps the definition in detail", () => {
    renderWorkspace();
    const card = document.querySelector('[data-finding-id="finding-1"]');
    expect(card.querySelector('[data-classification="insufficient_evidence"]')).toBeTruthy();
    expect(within(card).getByText("Insufficient evidence")).toBeTruthy();
    fireEvent.click(within(card).getByRole("button", { name: "Review" }));
    expect(screen.getAllByText("This historical finding was generated before contextual classification was available.").length).toBeGreaterThan(0);
  });

  it("renders classified metadata, top-three guidance, and Show all checks", () => {
    const guidance = Array.from({ length: 5 }, (_, index) => ({
      rank: index + 1,
      check: `Check ${index + 1}.`,
      reason: `Reason ${index + 1}.`,
      category: "data_quality",
      editable: true,
    }));
    const classified = {
      ...result.analysis_explanation.insights[0],
      classification: { type: "unexplained_systemic_change", confidence: "high", reasons: ["Comparable modes matched."] },
      data_confidence: { rating: "high", summary: "Quality checks passed." },
      operating_mode: { match: "strong", confidence: "high" },
      persistence: { persistent: true, duration: "18 days" },
      investigation_guidance: guidance,
      activity_timeline: [{ event_type: "analysis_window", title: "Recent comparison", period_label: "18 days", precision: "period" }],
    };
    renderWorkspace("/portfolio", {
      effectiveLatestUploadResult: { ...result, data_quality: { coverage_percent: 100 }, analysis_explanation: { ...result.analysis_explanation, insights: [classified] } },
    });

    const card = document.querySelector('[data-finding-id="finding-1"]');
    expect(card.querySelector('[data-classification="unexplained_systemic_change"]')).toBeTruthy();
    fireEvent.click(within(card).getByRole("button", { name: "Review" }));
    expect(document.querySelectorAll(".evidence-section .classification-guidance > li")).toHaveLength(5);
    const showAll = screen.getByText("Show all checks").closest("details");
    expect(showAll.open).toBe(false);
    expect(showAll.textContent).toContain("Check 4.");
    expect(screen.getByText("Recent comparison")).toBeTruthy();
  });

  it("keeps system navigation and unassigned-site compatibility", () => {
    renderWorkspace("/portfolio", { effectiveLatestUploadResult: { ...result, facility_name: undefined, site_name: undefined } });
    expect(screen.getByRole("heading", { name: "Unassigned Analysis" })).toBeTruthy();

    cleanup();
    renderWorkspace();
    const search = screen.getByRole("combobox", { name: /Search sites/i });
    fireEvent.change(search, { target: { value: "Cooling system" } });
    fireEvent.click(screen.getByRole("button", { name: "System: Cooling system" }));
    expect(screen.getByRole("heading", { name: "Cooling system" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Review" })).toBeTruthy();
  });

  it("shows a portfolio list only after more than one site is available", async () => {
    const apiFetch = vi.fn(async () => ({ ok: true, json: async () => ({ runs: [{
      run_id: "site-b-run", adaptive_site_key: "site-b", site_name: "South Plant", system_name: "Pumping",
      rows_received: 10, rows_accepted: 10, evidence_summary: [], observation_status: "normal", baseline_status: "Established",
    }] }) }));
    renderWorkspace("/portfolio", { apiFetch });

    expect(await screen.findByRole("heading", { name: "Sites" })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Open Site" })).toHaveLength(2);
  });
});
