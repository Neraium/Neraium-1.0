import React from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import EvidenceDashboard from "./EvidenceDashboard";
import MeasurableConsequence from "./MeasurableConsequence";
import quantified from "../../../tests/fixtures/measurable-consequence.json";

afterEach(cleanup);

describe("Measurable consequence", () => {
  it("renders the package result in the current dashboard with expandable technical evidence", () => {
    render(React.createElement(EvidenceDashboard, { summary: { title: "Flow response changed", measurableConsequence: quantified } }));
    const section = screen.getByRole("region", { name: "Measurable consequence" });
    expect(within(section).getByText("Water use above expected")).toBeTruthy();
    expect(within(section).getByText("12,840 gal")).toBeTruthy();
    expect(within(section).getByText("6.0 hours")).toBeTruthy();
    expect(within(section).getByText("High")).toBeTruthy();
    const details = section.querySelector("details");
    expect(details.open).toBe(false);
    fireEvent.click(within(section).getByText("Technical evidence"));
    expect(details.open).toBe(true);
    expect(within(section).getByText("water:load")).toBeTruthy();
    expect(within(section).getByText("water-flow / cooling-load")).toBeTruthy();
    expect(within(section).getByText(/1970-01-01T00:00:00.000Z/)).toBeTruthy();
    expect(within(section).getByText(/timestamp_aware_trapezoidal_integration/)).toBeTruthy();
    expect(section.textContent).not.toMatch(/cause|diagnos|saving|optimiz|corrective/i);
  });

  it.each([undefined, null, { status: "not_quantifiable" }, { ...quantified, cumulative_amount: null },
    { ...quantified, cumulative_amount: NaN }, { ...quantified, cumulative_amount: Infinity },
    { ...quantified, cumulative_amount: "12840" }, { ...quantified, cumulative_unit: "kWh" },
    { ...quantified, direction: "below_expected" }, { ...quantified, duration_seconds: 0 },
  ])("withholds unsupported numbers for %j", (result) => {
    render(React.createElement(MeasurableConsequence, { result }));
    expect(screen.getByText("Consequence not quantifiable from available evidence.")).toBeTruthy();
    expect(screen.queryByText("12,840 gal")).toBeNull();
  });

  it.each([[-5, "below_expected", "-5 gal"], [0, "aligned", "0 gal"]])("preserves signed amount %s", (value, direction, display) => {
    render(React.createElement(MeasurableConsequence, { result: { ...quantified, cumulative_amount: value, direction } }));
    expect(screen.getByText(display)).toBeTruthy();
  });

  it("shows actual limitations and unknown support without inventing confidence", () => {
    render(React.createElement(MeasurableConsequence, { result: { ...quantified, support_level: null, limitations: ["Mixed signed deviations.", "Unsupported gaps excluded."], skipped_interval_count: 2 } }));
    expect(screen.getByText("Not supplied")).toBeTruthy();
    expect(screen.getByText("Mixed signed deviations.")).toBeTruthy();
    expect(screen.getByText("Unsupported gaps excluded.")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
  });

  it("withholds amounts when the overall finding evidence is insufficient", () => {
    render(React.createElement(EvidenceDashboard, { variant: "insufficient", summary: { measurableConsequence: quantified } }));
    expect(screen.getByText("Consequence not quantifiable from available evidence.")).toBeTruthy();
    expect(screen.queryByText("12,840 gal")).toBeNull();
  });
});
