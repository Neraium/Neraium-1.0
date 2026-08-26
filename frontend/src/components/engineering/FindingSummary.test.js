/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import FindingSummary from "./FindingSummary";

afterEach(cleanup);

function compactCard(overrides = {}) {
  return {
    findingKey: "finding-1",
    systemContext: "Pressure distribution",
    assetContext: "Booster pump 2",
    title: "Pump response changed",
    behavior: "Pump demand no longer matches measured flow during comparable operation.",
    priority: "High",
    changeConfidence: "Qualified",
    materialLimitation: "Available evidence does not establish the physical cause.",
    reviewState: "Investigating",
    assignment: "Mechanical",
    primaryAction: { label: "Review finding", route: "/findings/finding-1" },
    ...overrides,
  };
}

describe("compact Results finding card", () => {
  it("renders only triage fields and one primary action", () => {
    const onReview = vi.fn();
    render(React.createElement(FindingSummary, { card: compactCard(), onReview }));
    const card = screen.getByTestId("compact-finding-card");
    for (const visible of ["System / asset", "Pressure distribution", "Booster pump 2", "Pump response changed", "Pump demand no longer matches measured flow", "High", "Change confidence", "Qualified", "Review state", "Investigating", "Assignment", "Mechanical", "Important limitation"]) {
      expect(card.textContent).toContain(visible);
    }
    expect(within(card).getAllByRole("button")).toHaveLength(1);
    expect(within(card).queryByRole("group")).toBeNull();
    expect(card.querySelector("details")).toBeNull();
    fireEvent.click(within(card).getByRole("button", { name: "Review finding" }));
    expect(onReview).toHaveBeenCalledWith("finding-1");
  });

  it("cannot render deep evidence fields that are absent from the card contract", () => {
    const hostile = compactCard();
    Object.assign(hostile, {
      rawVariables: ["RAW_SIGNAL_RESULTS_CANARY"],
      relationships: [{ baseline: 0.918273, current: 0.314159, samples: 997 }],
      generatedAt: "2026-08-25T05:23:56.206210+00:00",
      lineage: "LINEAGE_RESULTS_CANARY",
      engine: "ENGINE_RESULTS_CANARY",
      guidance: "GUIDANCE_RESULTS_CANARY",
      classification: "CLASSIFICATION_RESULTS_CANARY",
    });
    render(React.createElement(FindingSummary, { card: hostile }));
    const text = screen.getByTestId("compact-finding-card").textContent;
    for (const forbidden of ["RAW_SIGNAL_RESULTS_CANARY", "0.918273", "997", "2026-08-25", "LINEAGE_RESULTS_CANARY", "ENGINE_RESULTS_CANARY", "GUIDANCE_RESULTS_CANARY", "CLASSIFICATION_RESULTS_CANARY"]) expect(text).not.toContain(forbidden);
  });

  it("shows explicit review and assignment states while omitting an absent limitation", () => {
    render(React.createElement(FindingSummary, { card: compactCard({ reviewState: "Not reviewed", assignment: "Unassigned", materialLimitation: null }) }));
    const card = screen.getByTestId("compact-finding-card");
    expect(within(card).getByText("Review state")).toBeTruthy();
    expect(within(card).getByText("Not reviewed")).toBeTruthy();
    expect(within(card).getByText("Assignment")).toBeTruthy();
    expect(within(card).getByText("Unassigned")).toBeTruthy();
    expect(within(card).queryByText("Important limitation")).toBeNull();
    expect(card.querySelectorAll("section")).toHaveLength(1);
  });
});
