/* @vitest-environment jsdom */
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
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
