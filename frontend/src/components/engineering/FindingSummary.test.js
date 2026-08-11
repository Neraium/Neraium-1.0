/* @vitest-environment jsdom */
import React from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import FindingSummary from "./FindingSummary";

afterEach(cleanup);

describe("finding summary maintenance hierarchy", () => {
  it("uses display labels on the card and retains opaque identities outside maintenance copy", () => {
    const finding = {
      id: "source_finding_982",
      workflowFindingId: "canonical_73",
      title: "Pump response changed",
      observedChange: "Discharge response no longer matches comparable operation.",
      firstPlaceToLook: "Inspect the discharge pressure boundary.",
      status: "Change detected",
      objectType: "finding",
      tier: "Qualified",
      location: { asset: "Booster pump 2", system: "Pressure distribution", rawAsset: "pump_asset_02", rawSystem: "sys_pressure_01" },
      supporting: ["Measured relationship changed."],
      relationships: [{ label: "Flow and pressure" }],
      confidenceDimensions: {
        changeDetection: { level: "high" }, interpretation: { level: "low" }, operatingContext: { level: "high" },
      },
      classificationPresentation: { persistence: { label: "Persistent" } },
      operatingMode: { match: "comparable" },
    };
    render(React.createElement(FindingSummary, {
      finding,
      reviewRecord: { state: "investigating", priority: "critical", assignment: { kind: "team", label: "Mechanical" }, dueDate: "2026-08-22" },
      rankingExplanation: "Persistent change.",
    }));
    const card = screen.getByTestId("compact-finding-card");
    const labels = ["Equipment / system", "What changed", "Requested next action", "Priority", "Assignment", "Due", "Workflow", "Change", "Interpretation", "Persistence", "Context"];
    for (const label of labels) expect(within(card).getByText(label)).toBeTruthy();
    expect(within(card).getByText("Booster pump 2")).toBeTruthy();
    expect(within(card).getByText("Pressure distribution")).toBeTruthy();
    expect(card.textContent).not.toContain("source_finding_982");
    expect(card.textContent).not.toContain("pump_asset_02");
    expect(card.textContent).not.toContain("sys_pressure_01");
    expect(within(card).queryByText("Finding confidence")).toBeNull();
  });
});
