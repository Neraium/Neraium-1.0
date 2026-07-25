/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import OperatorInsightDetail from "./OperatorInsightDetail";

vi.mock("./RelationshipExplorer", () => ({ default: () => React.createElement("div", null, "Relationship explorer") }));

const h = React.createElement;

afterEach(() => cleanup());

function classifiedInsight(overrides = {}) {
  return {
    id: "systemic-pump-change",
    summary: "Pump relationship changed",
    system: "Pumping",
    sourceName: "pump-history.csv",
    classification: {
      type: "unexplained_systemic_change",
      confidence: "high",
      reasons: ["The relationship shift persisted under comparable conditions."],
      alternative_explanations: ["An undocumented control-state change."],
      certainty_limit: "This finding does not identify a cause or predict an exact failure.",
    },
    dataConfidence: { rating: "high", summary: "Quality checks passed.", reasons: [] },
    sensorHealth: [{ signal: "discharge_pressure", health: "healthy", conditions: [] }],
    operatingMode: {
      baseline_mode_label: "Lead-pump mid-load operation",
      recent_mode_label: "Lead-pump mid-load operation",
      match: "strong",
      confidence: "high",
      reasons: ["Pump state and load context matched."],
    },
    persistence: { persistent: true, duration: "18 days", summary: "The change remained present for 18 days." },
    activityTimeline: [{
      event_type: "analysis_window",
      title: "Relationship comparison period",
      detail: "The relationship was evaluated in the recorded recent window.",
      start: "2026-07-01T00:00:00Z",
      end: "2026-07-18T23:59:00Z",
      precision: "range",
    }],
    investigationGuidance: [
      { rank: 1, check: "Verify source data.", reason: "Source context bounds physical review.", category: "data_quality", editable: true },
      { rank: 2, check: "Review the timeline.", reason: "The change persisted under comparable modes.", category: "operating_context", editable: true },
      { rank: 3, check: "Inspect the pressure boundary.", reason: "The pressure relationship changed.", category: "physical_system", editable: true },
      { rank: 4, check: "Compare control states.", reason: "An undocumented state remains possible.", category: "controls", editable: true },
      { rank: 5, check: "Review maintenance notes.", reason: "Recent work can change context.", category: "documentation", editable: true },
    ],
    alternativeExplanations: ["An undocumented control-state change."],
    dataLimitations: ["Only uploaded telemetry and recorded context were evaluated."],
    contributingRelationships: [{ display_columns: ["Pump speed", "Discharge pressure"], change_type: "weakened" }],
    evidence: [{
      evidence_id: "ev-pressure",
      supporting_signals: ["Pump speed and discharge pressure changed together."],
      source_row_anchors: [120, 248],
      source_time_ranges: [{ current_start: "2026-07-01T00:00:00Z", current_end: "2026-07-18T23:59:00Z" }],
    }],
    ...overrides,
  };
}

describe("OperatorInsightDetail progressive disclosure", () => {
  it("keeps the initial investigation in the required five-section order", () => {
    const { container } = render(h(OperatorInsightDetail, { defaultOpen: true, insight: classifiedInsight() }));

    const headings = Array.from(container.querySelectorAll(".evidence-page__section > h4")).map((node) => node.textContent);
    expect(headings).toEqual([
      "What changed",
      "Why it matters",
      "Highest-value next checks",
      "Relationship timeline",
      "Supporting evidence",
    ]);
    expect(screen.getByText("Unexplained systemic change")).toBeTruthy();
    expect(screen.getByText("Persistent for 18 days")).toBeTruthy();
    expect(screen.getByText("Operating-mode match is strong.")).toBeTruthy();
  });

  it("collapses secondary context while retaining every evidence path", () => {
    render(h(OperatorInsightDetail, { defaultOpen: true, insight: classifiedInsight() }));

    for (const label of [
      "Why Neraium classified it this way",
      "Operating-mode comparison details",
      "Sensor-health details",
      "Alternative explanations",
      "Data limitations",
      "Source metadata",
      "Technical analysis details",
      "Audit history",
      "Open relationship evidence",
    ]) {
      const details = screen.getByText(label).closest("details");
      expect(details).toBeTruthy();
      expect(details.open).toBe(false);
    }

    const technical = screen.getByText("Technical analysis details").closest("details");
    fireEvent.click(technical.querySelector(":scope > summary"));
    expect(technical.open).toBe(true);
    expect(screen.getByText("Source row anchors")).toBeTruthy();
    expect(technical.textContent).toContain("120");
    expect(technical.textContent).toContain("248");
    expect(screen.getByText("Raw analysis payload")).toBeTruthy();
  });

  it("shows only the top three checks until Show all checks is opened", () => {
    const { container } = render(h(OperatorInsightDetail, { defaultOpen: true, insight: classifiedInsight() }));

    expect(container.querySelectorAll("#recommended-investigation > .investigation-guidance-list > li")).toHaveLength(3);
    const allChecks = screen.getByText("Show all checks").closest("details");
    expect(allChecks.open).toBe(false);
    expect(allChecks.textContent).toContain("Compare control states.");
    expect(allChecks.textContent).toContain("Review maintenance notes.");
    allChecks.querySelector("summary").focus();
    expect(document.activeElement).toBe(allChecks.querySelector("summary"));
    fireEvent.click(allChecks.querySelector("summary"));
    expect(allChecks.open).toBe(true);
  });

  it("keeps hydraulic and structured water evidence in the appropriate layers", () => {
    render(h(OperatorInsightDetail, {
      defaultOpen: true,
      insight: {
        ...classifiedInsight(),
        observedFacts: [
          "Pump power decreased -8.9%.",
          "Flow increased +6.3%.",
          "Main pressure decreased -4.7%.",
          "Filter dp decreased -32%.",
        ],
        changedRelationshipCount: 4,
        observedEvidence: [{ summary: "SII observed flow and differential-pressure relationship drift." }],
        derivedMetrics: [{ explanation: "Hydraulic output proxy is separate from electrical input." }],
        possibleExplanations: [{ explanation: "Valve-position change" }],
        recommendedChecksStructured: [{ check: "Check valve position and bypass status." }],
        confidenceAndUncertainty: { explanation: "Water interpretation confidence is Medium." },
      },
    }));

    expect(screen.getByText("The system produced more flow while recorded pump power and pressure decreased relative to the learned baseline.")).toBeTruthy();
    expect(screen.getByText("Pump power decreased 8.9% while flow increased 6.3%.")).toBeTruthy();
    expect(screen.getByText("Water intelligence")).toBeTruthy();
    expect(screen.getAllByText(/Hydraulic output proxy/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Valve-position change/i).length).toBeGreaterThan(0);
  });
});
