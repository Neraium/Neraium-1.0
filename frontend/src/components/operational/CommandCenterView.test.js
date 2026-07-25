/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CommandCenterView from "./CommandCenterView";

const h = React.createElement;

const helpers = {
  formatInsightTitle: (insight) => insight?.summary || insight?.title || "Operating behavior changed",
  insightRelationshipLabels: () => [],
  operatorSummaryBriefing: (insight) => [insight?.whatHappened || "Operating behavior changed from the learned baseline."],
};

function finding(overrides = {}) {
  return {
    id: "rush-pressure",
    system: "Rush Tower Water System",
    summary: "Pressure response changed during comparable operation.",
    severity: "high",
    confidence: "high",
    status: "Strengthening",
    whatHappened: "Pump speed and discharge pressure no longer follow their learned relationship.",
    recommendedFirstAction: "Verify source data and inspect the affected pressure boundary.",
    classification: { type: "unexplained_systemic_change", confidence: "high", reasons: ["Comparable operation matched."] },
    dataConfidence: { rating: "high" },
    operatingMode: { match: "strong" },
    persistence: { persistent: true, duration: "18 days" },
    ...overrides,
  };
}

function completedModel(overrides = {}) {
  return {
    insights: [finding()],
    uiState: { key: "analysisComplete" },
    analysisComplete: true,
    dashboardSystemCards: [
      { id: "rush", name: "Rush Tower Water System", status: "Review", activeInsights: 1 },
      { id: "quiet", name: "North Loop", status: "Normal", activeInsights: 0 },
    ],
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  window.innerWidth = 1024;
});

describe("CommandCenterView shift-start hierarchy", () => {
  it("renders a sparse no-data state with only the useful actions", () => {
    const onImportDataset = vi.fn();
    const onConnectLiveData = vi.fn();
    render(h(CommandCenterView, {
      model: { insights: [], uiState: { key: "noTelemetry" }, analysisComplete: false, dashboardSystemCards: [] },
      helpers,
      onOpenInvestigation: vi.fn(),
      onImportDataset,
      onConnectLiveData,
    }));

    expect(screen.getByRole("heading", { name: "Baseline not established" })).toBeTruthy();
    expect(screen.getByText("Import telemetry to begin comparison.")).toBeTruthy();
    expect(screen.queryByText(/evidence quality/i)).toBeNull();
    expect(screen.queryByRole("heading", { name: "Analysis Details" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Import dataset" }));
    fireEvent.click(screen.getByRole("button", { name: "Connect telemetry" }));
    expect(onImportDataset).toHaveBeenCalledTimes(1);
    expect(onConnectLiveData).toHaveBeenCalledTimes(1);
  });

  it("renders the quiet state without manufacturing urgency", () => {
    render(h(CommandCenterView, { model: completedModel({ insights: [] }), helpers, onOpenInvestigation: vi.fn() }));

    expect(screen.getByRole("heading", { name: "No new unexplained system changes." })).toBeTruthy();
    expect(screen.getByText("All monitored systems are quiet.")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Quiet systems" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Review" })).toBeNull();
  });

  it("keeps an instrumentation issue quiet but available for review", () => {
    render(h(CommandCenterView, {
      model: completedModel({ insights: [finding({
        id: "pressure-tx",
        severity: "moderate",
        status: "Open",
        classification: { type: "possible_instrumentation_issue", confidence: "high", reasons: ["Peer divergence recorded."] },
      })] }),
      helpers,
      onOpenInvestigation: vi.fn(),
    }));

    expect(screen.getByText("1 instrumentation issue remains under review.")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Needs attention" })).toBeTruthy();
    expect(screen.getByText("Possible instrumentation issue")).toBeTruthy();
  });

  it("renders one serious finding as a compact evidence-backed card", () => {
    render(h(CommandCenterView, { model: completedModel(), helpers, onOpenInvestigation: vi.fn() }));

    expect(screen.getByRole("heading", { name: "Escalated engineering review" })).toBeTruthy();
    const card = screen.getByTestId("compact-finding-card");
    expect(within(card).getByText("Rush Tower Water System")).toBeTruthy();
    expect(within(card).getByRole("heading", { name: "Pressure response changed during comparable operation." })).toBeTruthy();
    expect(within(card).getByText("Unexplained systemic change")).toBeTruthy();
    expect(within(card).getByText("High confidence")).toBeTruthy();
    expect(within(card).getByText("Strengthening")).toBeTruthy();
    expect(card.querySelectorAll(".shift-finding-card__evidence")).toHaveLength(1);
    expect(card.querySelectorAll(".shift-finding-card__next p")).toHaveLength(1);
    expect(card.textContent).not.toContain("Comparable operation matched");
    expect(card.textContent).not.toContain("18 days");
  });

  it("keeps review, acknowledgement, and evidence access keyboard-visible", () => {
    const onOpenInvestigation = vi.fn();
    render(h(CommandCenterView, { model: completedModel(), helpers, onOpenInvestigation }));

    const review = screen.getByRole("button", { name: "Review" });
    const acknowledge = screen.getByRole("button", { name: "Acknowledge" });
    const evidence = screen.getByRole("button", { name: "View evidence" });
    review.focus();
    expect(document.activeElement).toBe(review);
    fireEvent.click(review);
    fireEvent.click(evidence);
    expect(onOpenInvestigation).toHaveBeenNthCalledWith(1, "rush-pressure");
    expect(onOpenInvestigation).toHaveBeenNthCalledWith(2, "rush-pressure", { focusTarget: "insight-evidence" });
    fireEvent.click(acknowledge);
    expect(screen.getByRole("button", { name: "Acknowledged" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("heading", { name: "Monitoring" })).toBeTruthy();
  });

  it("preserves the conservative legacy fallback and mobile card structure", () => {
    window.innerWidth = 390;
    render(h(CommandCenterView, {
      model: completedModel({
        insights: [finding({ classification: undefined, dataConfidence: undefined, operatingMode: undefined, persistence: undefined })],
        dashboardSystemCards: { id: "legacy-object" },
      }),
      helpers,
      onOpenInvestigation: vi.fn(),
    }));

    const card = screen.getByTestId("compact-finding-card");
    expect(within(card).getByText("Insufficient evidence")).toBeTruthy();
    expect(card.querySelector("[data-classification='insufficient_evidence']")).toBeTruthy();
    expect(within(card).getAllByRole("button")).toHaveLength(3);
    expect(screen.queryByRole("heading", { name: "Quiet systems" })).toBeNull();
  });
});
