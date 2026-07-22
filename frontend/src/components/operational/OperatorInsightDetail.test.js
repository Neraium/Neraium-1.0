/* @vitest-environment jsdom */
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import OperatorInsightDetail from "./OperatorInsightDetail";

vi.mock("./RelationshipExplorer", () => ({ default: () => React.createElement("div", null, "Relationship explorer") }));

const h = React.createElement;

afterEach(() => cleanup());

describe("OperatorInsightDetail water intelligence", () => {
  it("labels observed, derived, hypothesis, check, confidence, and confirmation state", () => {
    render(h(OperatorInsightDetail, {
      defaultOpen: true,
      insight: {
        id: "water-pump",
        summary: "Pump hydraulic behavior changed",
        severity: "moderate",
        confidence: "Medium",
        system: "Pumping",
        relationshipPriorId: "water.pump_hydraulic_behavior",
        relationshipPriorVersion: "1.0.0",
        operatingMode: "normal",
        graphTrust: { tier: "proposed" },
        hypothesisStatus: "observed",
        observedEvidence: [{ summary: "SII observed flow and differential-pressure relationship drift." }],
        derivedMetrics: [{ name: "hydraulic_output_proxy", explanation: "Hydraulic output proxy is separate from electrical input." }],
        possibleExplanations: [{ explanation: "Valve-position change", hypothesis_state: "suspected" }],
        confoundingConditions: [{ condition: "valve position changes", state: "active" }],
        recommendedChecksStructured: [{ check: "Check valve position and bypass status." }],
        confidenceAndUncertainty: { explanation: "Water interpretation confidence is Medium." },
      },
    }));

    expect(screen.getByText("Water intelligence")).toBeTruthy();
    expect(screen.getAllByText("Observed").length).toBeGreaterThan(0);
    expect(screen.getByText("Derived")).toBeTruthy();
    expect(screen.getByText("Possible explanation")).toBeTruthy();
    expect(screen.getByText("Recommended check")).toBeTruthy();
    expect(screen.getByText("Operator confirmed")).toBeTruthy();
    expect(screen.getAllByText("No").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/SII observed flow and differential-pressure relationship drift/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Hydraulic output proxy/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Valve-position change/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Check valve position and bypass status/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Water interpretation confidence is Medium/i).length).toBeGreaterThan(0);
  });
});
