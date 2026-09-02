/* @vitest-environment jsdom */
import React from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import EvidenceDashboard from "./EvidenceDashboard";

afterEach(cleanup);

function summary(overrides = {}) {
  return {
    title: "Authoritative hydraulic response finding",
    system: "Primary chilled-water plant",
    status: "Persistent change detected",
    evidenceWindow: { label: "Aug 20 – Aug 25, 2026", start: "2026-08-20T00:00:00Z", end: "2026-08-25T05:23:56Z" },
    metrics: {
      magnitude: { value: 0.125, signed: true, description: "relationship shift" },
      persistence: { value: "Sustained", description: "across evaluation window" },
      operatingContext: { value: "Comparable", description: "operating conditions" },
      confidence: { value: "Strong", description: "supporting evidence" },
    },
    relationships: [
      { id: "one", label: "Flow ↔ Pressure", magnitude: 0.125, signed: true, sparkline: [{ timestamp: "2026-08-22T00:00:00Z", value: 4 }, { timestamp: "2026-08-20T00:00:00Z", value: 2 }, { timestamp: "2026-08-21T00:00:00Z", value: 3 }] },
      { id: "two", label: "Pump power ↔ Flow", magnitude: -0.32, signed: true, sparkline: null },
      { id: "three", label: "Valve position ↔ Demand", magnitude: null, signed: false, sparkline: [] },
      { id: "four", label: "Never ↔ Rendered", magnitude: 9, signed: true },
    ],
    cause: { established: false, label: "No — investigation required" },
    ...overrides,
  };
}

describe("EvidenceDashboard", () => {
  it("renders the exact compact dashboard hierarchy and truthful signed relationship values", () => {
    const { container } = render(React.createElement(EvidenceDashboard, { summary: summary() }));
    expect(screen.getByText("Finding")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1, name: "Authoritative hydraulic response finding" })).toBeTruthy();
    const context = screen.getByLabelText("Finding context");
    for (const value of ["Primary chilled-water plant", "Persistent change detected", "Aug 20 – Aug 25, 2026"]) expect(within(context).getByText(value)).toBeTruthy();
    const metrics = screen.getByLabelText("Evidence metrics");
    for (const value of ["+0.13", "Sustained", "Comparable", "Strong"]) expect(within(metrics).getByText(value)).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: "Strongest Relationship Changes" })).toBeTruthy();
    expect(screen.getAllByText("+0.13")).toHaveLength(2);
    expect(screen.getByText("-0.32")).toBeTruthy();
    expect(screen.getByText("Not supplied")).toBeTruthy();
    expect(screen.queryByText("Never ↔ Rendered")).toBeNull();
    expect(screen.getByText("No — investigation required")).toBeTruthy();
    expect(screen.getByText("Behavior change evidence")).toBeTruthy();
    expect(screen.getAllByText("Review-safe relationship summary")).toHaveLength(3);
    expect(document.body.textContent).not.toMatch(/baseline|sample count|signal id|lineage/i);
    expect(container.querySelectorAll(".evidence-dashboard__context-cell")).toHaveLength(3);
    expect(container.querySelectorAll(".evidence-dashboard__metric")).toHaveLength(4);
  });

  it("draws only real valid sparkline points with an accessible chronological summary", () => {
    const { container } = render(React.createElement(EvidenceDashboard, { summary: summary() }));
    const sparkline = screen.getByRole("img", { name: "Flow ↔ Pressure trend rises across 3 chronological evidence points." });
    expect(sparkline).toBeTruthy();
    expect(sparkline.querySelector("polyline")?.getAttribute("points")).toBe("4,26 50,16 96,6");
    expect(container.querySelectorAll(".evidence-dashboard__sparkline")).toHaveLength(1);
    expect(within(screen.getByText("Pump power ↔ Flow").closest("li")).queryByRole("img")).toBeNull();
    expect(within(screen.getByText("Valve position ↔ Demand").closest("li")).queryByRole("img")).toBeNull();
  });

  it("omits malformed sparkline evidence instead of fabricating a decorative trend", () => {
    const invalid = summary({ relationships: [{ id: "bad", label: "Flow ↔ Pressure", magnitude: null, sparkline: [{ timestamp: "not-a-date", value: 1 }, { timestamp: "2026-08-21T00:00:00Z", value: 2 }] }] });
    const { container } = render(React.createElement(EvidenceDashboard, { summary: invalid }));
    expect(container.querySelector(".evidence-dashboard__sparkline")).toBeNull();
    expect(screen.getByText("Not supplied")).toBeTruthy();
  });

  it("uses explicit unsupported states and never strengthens missing evidence", () => {
    const unsupported = summary({
      metrics: {
        magnitude: { value: null, label: "Not established", description: "relationship magnitude unavailable" },
        persistence: { value: "Not established", description: "persistence evidence unavailable" },
        operatingContext: { value: "Insufficient evidence", description: "comparability evidence unavailable" },
        confidence: { value: "Unavailable", description: "confidence evidence unavailable" },
      },
      relationships: [],
      cause: {},
    });
    render(React.createElement(EvidenceDashboard, { summary: unsupported }));
    expect(screen.getAllByText("Not established")).toHaveLength(2);
    expect(screen.getByText("Insufficient evidence")).toBeTruthy();
    expect(screen.getByText("Unavailable")).toBeTruthy();
    expect(screen.getByText("No authoritative relationship changes were supplied.")).toBeTruthy();
    expect(screen.getByText("No — investigation required")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/probable|likely cause/i);
  });

  it("shows confirmed cause language only when the supplied cause contract confirms it", () => {
    render(React.createElement(EvidenceDashboard, { summary: summary({ cause: { established: true, label: "Yes — confirmed in evidence" } }) }));
    const answer = screen.getByText("Yes — confirmed in evidence");
    expect(answer.getAttribute("data-established")).toBe("true");
  });

  it("renders a reduced insufficient record without unsupported finding metrics or cause claims", () => {
    render(React.createElement(EvidenceDashboard, { variant: "insufficient", summary: summary({ insufficient: { title: "Insufficient evidence", description: "Comparable operating history was not available." } }) }));
    expect(screen.getByRole("heading", { level: 1, name: "Insufficient evidence" })).toBeTruthy();
    expect(screen.getByText("Comparable operating history was not available.")).toBeTruthy();
    expect(screen.queryByLabelText("Evidence metrics")).toBeNull();
    expect(screen.queryByText("Cause established?")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Strongest Relationship Changes" })).toBeNull();
  });
});
