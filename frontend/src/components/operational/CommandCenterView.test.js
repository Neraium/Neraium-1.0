/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CommandCenterView from "./CommandCenterView";

const h = React.createElement;

const helpers = {
  formatInsightTitle: (insight) => insight?.summary || insight?.title || "Operating behavior changed",
  insightRelationshipLabels: () => [],
  operatorSummaryBriefing: (insight) => [insight?.whatHappened || "Operating behavior changed from the learned baseline."],
  formatConfidenceDisplay: (label, score) => label || (score ? String(score) : ""),
  severityToTone: (severity) => String(severity || "low").toLowerCase(),
};

function completedModel(overrides = {}) {
  return {
    insights: [{
      id: "stale-card-finding",
      summary: "Operating behavior changed",
      severity: "high",
      confidenceScore: 0.91,
      whatHappened: "Operating behavior changed during hydration.",
      recommendedFirstAction: "Review the supporting evidence.",
      evidence: [],
      observedFacts: [],
      publicEvidenceItems: [],
    }],
    uiState: { key: "analysisComplete" },
    analysisComplete: true,
    behaviorState: "Behavior Shift Detected",
    dashboardSystemCards: [{ id: "system-1", name: "Pump system", status: "Critical", activeInsights: "1" }],
    lastAnalysis: "Jul 19, 2026, 4:48 AM UTC",
    telemetryStatus: { label: "Telemetry acceptable" },
    dataCoveragePercent: 100,
    analysisHistory: [],
    historyItems: [],
    dataSourceRows: [],
    analysisMetadataRows: [],
    behaviorWindowRows: [],
    rawResultJson: "{}",
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("CommandCenterView hydration regressions", () => {
  it("renders a compact operational no-data state", () => {
    const onImportDataset = vi.fn();
    const onConnectLiveData = vi.fn();
    const { container } = render(h(CommandCenterView, {
      model: {
        insights: [],
        uiState: { key: "noTelemetry" },
        analysisComplete: false,
        dashboardSystemCards: [],
        commandCenterMessage: "Import a telemetry dataset, then run an analysis to establish the facility's behavior baseline.",
      },
      helpers,
      selectedInsight: null,
      onOpenInvestigation: vi.fn(),
      onImportDataset,
      onConnectLiveData,
    }));

    expect(screen.getByText("Awaiting data")).toBeTruthy();
    expect(screen.queryByText("Watching")).toBeNull();
    expect(screen.getByText("Not established")).toBeTruthy();
    expect(screen.getByText("No data available")).toBeTruthy();
    expect(screen.getByText("No active status available")).toBeTruthy();
    expect(screen.getByText("None active")).toBeTruthy();
    expect(screen.queryByText("Primary action")).toBeNull();
    expect(screen.queryByText("Secondary action")).toBeNull();
    const actionButtons = container.querySelectorAll(".operating-state-card__actions button");
    expect(actionButtons).toHaveLength(2);
    expect(actionButtons[0].textContent).toBe("Import dataset");
    expect(actionButtons[0].classList.contains("command-button")).toBe(true);
    expect(actionButtons[1].textContent).toBe("Connect telemetry");
    expect(actionButtons[1].classList.contains("secondary-command-button")).toBe(true);
    expect(container.querySelectorAll(".command-section")).toHaveLength(3);
    expect(screen.queryByRole("heading", { name: "Discovered Systems" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Analysis Details" })).toBeNull();
    expect(screen.queryByText(/Import a telemetry dataset, then run an analysis/i)).toBeNull();
    expect(screen.queryByText(/Evidence quality is separate from finding confidence/i)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Import dataset" }));
    expect(onImportDataset).toHaveBeenCalledTimes(1);
    expect(onConnectLiveData).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Connect telemetry" }));
    expect(onConnectLiveData).toHaveBeenCalledTimes(1);
    expect(onImportDataset).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["an imported dataset", false],
    ["connected telemetry", true],
  ])("preserves the pre-analysis actions for %s", (_state, telemetryConnected) => {
    render(h(CommandCenterView, {
      model: {
        insights: [],
        uiState: { key: "readyToAnalyze" },
        analysisComplete: false,
        telemetryConnected,
        dashboardSystemCards: [],
        telemetryStatus: { label: "No telemetry" },
        analysisMetadataRows: [],
        behaviorWindowRows: [],
      },
      helpers,
      selectedInsight: null,
      onOpenInvestigation: vi.fn(),
      onConnectLiveData: vi.fn(),
    }));

    expect(screen.getByText("Watching")).toBeTruthy();
    expect(screen.getByText("No telemetry")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Connect Live Telemetry" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Import and Analyze Dataset" })).toBeTruthy();
    expect(screen.queryByText("Awaiting data")).toBeNull();
    expect(screen.queryByText("No data available")).toBeNull();
  });

  it("renders a completed finding when dashboard system cards are not an array", () => {
    render(h(CommandCenterView, {
      model: completedModel({ dashboardSystemCards: { id: "stale-object", activeInsights: "1", name: "Legacy card" } }),
      helpers,
      selectedInsight: null,
      onSelectInsight: vi.fn(),
      onConnectLiveData: vi.fn(),
      onFocusInvestigation: vi.fn(),
    }));

    expect(screen.getByTestId("operational-command-center")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Operational Fingerprint Summary" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Prioritized Finding" })).toBeTruthy();
    expect(screen.getAllByText("Operating behavior changed").length).toBeGreaterThan(0);
    expect(screen.getByText("No systems are listed because no completed telemetry analysis is active.")).toBeTruthy();
  });
});
