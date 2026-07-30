/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import BaselineDetailView from "./BaselineDetailView";

const h = React.createElement;

afterEach(cleanup);

const routeIdentity = { portfolioId: "default", systemId: "chiller-system", baselineId: "bdm-v5-d5556684" };
const baselineResult = {
  portfolio_id: "default",
  system_id: "chiller-system",
  baseline_id: "bdm-v5-d5556684",
  filename: "resort chw baseline.csv",
  activation: { state: "active" },
  analysis_state: { status: "empty", count: 0, analyses: [] },
  candidate_model: {
    model_id: "bdm-v5-d5556684",
    baseline_id: "bdm-v5-d5556684",
    version: 5,
    source: { portfolio_id: "default", system_id: "chiller-system", row_count: 2016 },
    telemetry_schema: { numeric_columns: ["chw_supply_temp_f", "pump_speed_pct"] },
    relationship_graph: { edges: [{ edge_id: "edge-1", source: "chw_supply_temp_f", target: "pump_speed_pct", strength: 0.82, sample_count: 2016 }] },
    operating_modes: [{ mode_id: "mode-1", label: "occupied", sample_count: 1400, sample_fraction: 0.69 }],
    data_quality: { readiness: "ready", reliability_rating: "high", reliability_score: 97, timestamp_detected: true },
    timestamp_quality: { first_timestamp: "2026-01-01T00:00:00Z", last_timestamp: "2026-01-08T00:00:00Z", estimated_sample_interval: "5 minutes" },
  },
};

describe("baseline-only detail state", () => {
  it("renders the learned model and an explicit empty comparison state without unrelated findings", () => {
    render(h(BaselineDetailView, { routeIdentity, detailState: { status: "ready", result: baselineResult }, onRetry: () => {}, onImportComparison: () => {}, onReturnToPortfolio: () => {} }));

    expect(screen.getByRole("heading", { name: "Baseline Established", level: 3 })).toBeTruthy();
    expect(screen.getByText(/learned the system’s normal operating relationships/i)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Waiting for comparison data" })).toBeTruthy();
    expect(screen.getByText("resort chw baseline.csv")).toBeTruthy();
    expect(screen.getByText("chw_supply_temp_f")).toBeTruthy();
    expect(screen.getByText("pump_speed_pct")).toBeTruthy();
    expect(screen.getByText("97%", { selector: "dd" })).toBeTruthy();
    expect(screen.queryByText(/^Findings$/i)).toBeNull();
    expect(screen.queryByText(/Pumping System/i)).toBeNull();
    expect(screen.queryByText(/items in review/i)).toBeNull();
    expect(screen.queryByText(/being monitored/i)).toBeNull();
    expect(screen.queryByText(/differential_pressure_psi/i)).toBeNull();
  });

  it("offers comparison import and exposes bounded failure diagnostics with retry", () => {
    const onImportComparison = vi.fn();
    const onRetry = vi.fn();
    const { rerender } = render(h(BaselineDetailView, { routeIdentity, detailState: { status: "ready", result: baselineResult }, onRetry, onImportComparison, onReturnToPortfolio: () => {} }));

    fireEvent.click(screen.getByRole("button", { name: "Upload Comparison Dataset" }));
    expect(onImportComparison).toHaveBeenCalledTimes(1);

    rerender(h(BaselineDetailView, { routeIdentity, detailState: { status: "error", message: "The baseline service did not respond within 15 seconds. Retry the request.", errorType: "timeout", httpStatus: 408, requestId: "request-123" }, onRetry, onImportComparison, onReturnToPortfolio: () => {} }));
    expect(screen.getByRole("alert").textContent).toContain("timeout");
    expect(screen.getByRole("alert").textContent).toContain("408");
    expect(screen.getByRole("alert").textContent).toContain("request-123");
    fireEvent.click(screen.getByRole("button", { name: "Retry Baseline" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
