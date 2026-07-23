/* @vitest-environment jsdom */
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import OperatorInsightDetail from "./OperatorInsightDetail";

vi.mock("./RelationshipExplorer", () => ({ default: () => React.createElement("div", null, "Relationship explorer") }));

const h = React.createElement;

afterEach(() => cleanup());

describe("OperatorInsightDetail evidence synthesis", () => {
  it("synthesizes hydraulic evidence into the bounded operator page", () => {
    const relationshipWindow = [{
      current_start: "2026-02-11T23:00:00Z",
      current_end: "2026-03-01T23:00:00Z",
    }];
    render(h(OperatorInsightDetail, {
      defaultOpen: true,
      insight: {
        id: "pump-demand",
        summary: "Pump demand no longer matches flow",
        system: "Flow and pressure",
        changedRelationshipCount: 4,
        facilityTimezone: "UTC",
        observedFacts: [
          "Pump power decreased -8.9%.",
          "Flow increased +6.3%.",
          "Main pressure decreased -4.7%.",
          "Filter dp decreased -32%.",
          "Pump speed rpm decreased -1.4%.",
        ],
        qualityWarnings: ["Some columns could not be mapped to a generic signal category."],
        unmappedColumns: ["unmapped_vendor_state"],
        contributingRelationships: [
          { display_columns: ["Pump power", "Filter dp"], change_type: "missing", baseline_strength: "strong", current_strength: "weak" },
          { display_columns: ["Main pressure", "Filter dp"], change_type: "missing", baseline_strength: "strong", current_strength: "weak" },
          { display_columns: ["Pump power", "Flow"], change_type: "new", baseline_strength: "weak", current_strength: "strong" },
          { display_columns: ["Main pressure", "Flow"], change_type: "weakened", baseline_strength: "strong", current_strength: "moderate" },
        ],
        evidence: Array.from({ length: 4 }, () => ({ source_time_ranges: relationshipWindow })),
      },
    }));

    expect(screen.getByText("Change detected")).toBeTruthy();
    expect(screen.getByText("Narrowed")).toBeTruthy();
    expect(screen.getByText(/Unassigned dataset/).textContent).toContain("Flow and pressure");
    expect(screen.getByText("The system produced more flow while recorded pump power and pressure decreased relative to the learned baseline.")).toBeTruthy();
    expect(screen.getByText("Pump power decreased 8.9% while flow increased 6.3%.")).toBeTruthy();
    expect(screen.getByText("Main pressure decreased 4.7%.")).toBeTruthy();
    expect(screen.getByText("Filter differential pressure decreased 32%.")).toBeTruthy();
    expect(screen.getByText("Four learned hydraulic relationships weakened or changed.")).toBeTruthy();
    expect(screen.getByText(/producing more flow with less recorded pump power and lower pressure readings/i)).toBeTruthy();
    expect(screen.getByText(/Confirm whether pump operating mode, valve position, or sensor configuration changed/i)).toBeTruthy();
    expect(screen.getByText(/If no operating change occurred, compare pump power, flow, main pressure/i)).toBeTruthy();
    expect(screen.getByText("Some telemetry fields could not be classified, which limits how specifically Neraium can interpret the change.")).toBeTruthy();
    expect(screen.getAllByText("Feb 11 at 11:00 PM – Mar 1 at 11:00 PM").length).toBeGreaterThan(0);
    expect(screen.getByText("Open relationship evidence")).toBeTruthy();
    expect(screen.getByText("The relationship between pump power and filter differential pressure weakened from strong to weak.")).toBeTruthy();
    expect(screen.getByText("A stronger relationship emerged between pump power and flow.")).toBeTruthy();
    expect(screen.getByText("Technical details")).toBeTruthy();
    expect(screen.getByText("unmapped_vendor_state")).toBeTruthy();
    const defaultViewText = Array.from(document.querySelectorAll(".evidence-page__section")).map((node) => node.textContent).join(" ");
    expect(defaultViewText).not.toMatch(/decreased -|increased \+|operating coupling missing|operating coupling new/);
  });

  it("keeps structured water interpretation inside technical details", () => {
    render(h(OperatorInsightDetail, {
      defaultOpen: true,
      insight: {
        id: "water-pump",
        summary: "Pump hydraulic behavior changed",
        severity: "moderate",
        confidence: "Medium",
        system: "Pumping",
        observedEvidence: [{ summary: "SII observed flow and differential-pressure relationship drift." }],
        derivedMetrics: [{ name: "hydraulic_output_proxy", explanation: "Hydraulic output proxy is separate from electrical input." }],
        possibleExplanations: [{ explanation: "Valve-position change" }],
        recommendedChecksStructured: [{ check: "Check valve position and bypass status." }],
        confidenceAndUncertainty: { explanation: "Water interpretation confidence is Medium." },
      },
    }));

    expect(screen.getByText("Technical details")).toBeTruthy();
    expect(screen.getByText("Water intelligence")).toBeTruthy();
    expect(screen.getByText("Observed")).toBeTruthy();
    expect(screen.getByText("Derived")).toBeTruthy();
    expect(screen.getByText("Possible explanation")).toBeTruthy();
    expect(screen.getByText("Recommended check")).toBeTruthy();
    expect(screen.getAllByText(/SII observed flow and differential-pressure relationship drift/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Hydraulic output proxy/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Valve-position change/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Check valve position and bypass status/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Water interpretation confidence is Medium/i).length).toBeGreaterThan(0);
  });
});
