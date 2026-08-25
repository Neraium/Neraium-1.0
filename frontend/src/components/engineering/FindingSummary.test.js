/* @vitest-environment jsdom */
import React from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import FindingSummary from "./FindingSummary";

afterEach(cleanup);

function supportedFinding(overrides = {}) {
  return {
    id: "finding-1",
    title: "Pump response changed",
    observedChange: "Pump demand no longer matches measured flow.",
    firstPlaceToLook: "Verify the flow transmitter against the local indicator.",
    recommendedFirstAction: "Verify the flow transmitter against the local indicator.",
    recommendationAllowed: true,
    status: "Change detected",
    objectType: "finding",
    tier: "Qualified",
    primaryLimitation: "Telemetry does not establish the cause of the change.",
    location: { asset: "Booster pump 2", system: "Pressure distribution", rawAsset: "pump_asset_02", rawSystem: "sys_pressure_01" },
    visibleSupporting: [
      "Pump demand increased 12%.",
      "Measured flow decreased 7%.",
      "The learned pump-demand / flow relationship changed.",
    ],
    supporting: ["Pump demand increased 12%.", "Measured flow decreased 7%.", "The learned pump-demand / flow relationship changed."],
    relationships: [{ id: "rel-1", source: "Pump demand", target: "Measured flow" }],
    confidenceDimensions: { changeDetection: { level: "high" } },
    classificationPresentation: { persistence: { label: "Persistent" } },
    operatingMode: { baseline_mode: "occupied cooling", recent_mode: "occupied cooling", match: "strong" },
    siiEvidence: { phase_4: { status: "available" }, provenance: { analysis_run_id: "run-private" } },
    ...overrides,
  };
}

describe("finding summary evidence hierarchy", () => {
  it("shows compact structured finding evidence without deep technical records", () => {
    const finding = supportedFinding();
    render(React.createElement(FindingSummary, {
      finding,
      reviewRecord: { state: "investigating", priority: "critical", assignment: { kind: "team", label: "Mechanical" }, dueDate: "2026-08-22" },
    }));
    const card = screen.getByTestId("compact-finding-card");
    for (const section of ["Equipment / system", "Finding", "Requested next action", "Why this needs attention", "Priority", "Assignment", "Change confidence", "Evidence and limitations"]) {
      expect(within(card).getByText(section)).toBeTruthy();
    }
    expect(within(card).getByText("Change detected")).toBeTruthy();
    expect(within(card).getByRole("heading", { name: "Pump response changed." })).toBeTruthy();
    expect(within(card).getAllByText("Occupied Cooling", { selector: "dd" })).toHaveLength(2);
    expect(within(card).getAllByRole("listitem")).toHaveLength(3);
    expect(card.textContent).toContain("Telemetry does not establish the cause");
    expect(card.textContent).toContain("Verify the flow transmitter");
    expect(card.textContent).not.toContain("Due");
    expect(card.textContent).not.toContain("Workflow");
    expect(card.textContent).not.toMatch(/phase 4|provenance|analysis_run|run-private|pump_asset_02|sys_pressure_01/i);
  });

  it("does not present a supported claim or next step when evidence is explicitly insufficient", () => {
    render(React.createElement(FindingSummary, {
      finding: supportedFinding({ status: "Evidence insufficient", tier: "Withheld", recommendationAllowed: false }),
    }));
    const card = screen.getByTestId("compact-finding-card");
    expect(within(card).getByText("Evidence insufficient")).toBeTruthy();
    expect(within(card).getByRole("heading", { name: "Evidence insufficient for reliable interpretation" })).toBeTruthy();
    expect(card.textContent).not.toContain("Pump demand no longer matches measured flow");
    expect(within(card).queryByText("Requested next action")).toBeNull();
  });
});
