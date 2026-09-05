/* @vitest-environment jsdom */
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import FindingClassificationSummary from "./FindingClassificationSummary";

const cases = [
  ["known_operational_change", "Known operational change", "known", "Informational review"],
  ["context_limited_relationship_change", "Context-limited relationship change", "context", "Context review"],
  ["possible_instrumentation_issue", "Possible instrumentation issue", "instrumentation", "Verify instrumentation"],
  ["unexplained_systemic_change", "Unexplained systemic change", "systemic", "Engineering review"],
  ["observed_change_under_review", "Observed change under review", "context", "Monitoring review"],
  ["insufficient_evidence", "Insufficient evidence", "insufficient", "Evidence review"],
];

afterEach(() => cleanup());

describe("FindingClassificationSummary", () => {
  it.each(cases)("renders %s with the expected tone", (type, label, tone, priority) => {
    const { container } = render(React.createElement(FindingClassificationSummary, {
      finding: {
        classification: { type, label, confidence: type === "insufficient_evidence" ? "low" : "high" },
        dataConfidence: { rating: "high" },
        operatingMode: { match: "strong" },
        persistence: { persistent: true, duration: "18 days" },
      },
    }));

    expect(screen.getByText(label)).toBeTruthy();
    expect(screen.getByText(priority)).toBeTruthy();
    expect(screen.getByText("Persistent")).toBeTruthy();
    expect(container.querySelector(`.finding-classification--${tone}`)).toBeTruthy();
    expect(screen.getByLabelText(new RegExp(`Classification: ${label}`, "i"))).toBeTruthy();
    expect(screen.getAllByLabelText(/Data confidence: High/i).length).toBeGreaterThan(0);
  });

  it("never assigns the systemic treatment a critical or red class", () => {
    const { container } = render(React.createElement(FindingClassificationSummary, {
      finding: { classification: { type: "unexplained_systemic_change", confidence: "high" } },
    }));

    const summary = container.querySelector("[data-classification='unexplained_systemic_change']");
    expect(summary.className).toContain("finding-classification--systemic");
    expect(summary.className).not.toMatch(/critical|danger|red/);
  });

  it("does not present an evidence-window duration as unestablished persistence", () => {
    render(React.createElement(FindingClassificationSummary, {
      finding: {
        classification: { type: "context_limited_relationship_change", confidence: "limited" },
        persistence: { persistent: false, status: "not_established", duration: "81 days" },
        trajectory: { state: "Strengthening", scope: "evidence_support" },
      },
    }));

    expect(screen.getAllByText("Not established").length).toBeGreaterThan(0);
    expect(screen.getByText("Support trend")).toBeTruthy();
    expect(screen.getByText("Increasing")).toBeTruthy();
    expect(screen.queryByText("81 days")).toBeNull();
    expect(screen.queryByText(/^Trajectory$/)).toBeNull();
  });

  it("renders independent maintenance confidence dimensions without a vague aggregate", () => {
    render(React.createElement(FindingClassificationSummary, {
      finding: {
        classification: { type: "observed_change_under_review", confidence: "limited" },
        confidence: "limited",
        confidenceDimensions: {
          changeDetection: { level: "high" },
          interpretation: { level: "low", attribution_status: "unattributed" },
          operatingContext: { level: "high" },
          evidenceQuality: { level: "medium" },
        },
        persistence: { status: "observing", reason: "A follow-up window is required." },
        supportTrend: "increasing",
      },
    }));

    expect(screen.getByText("High", { selector: "dd" })).toBeTruthy();
    expect(screen.queryByText("Cause")).toBeNull();
    expect(screen.queryByText("Cause")).toBeNull();
    expect(screen.getByTestId("finding-classification-summary").getAttribute("aria-label")).not.toMatch(/cause|diagnosis/i);
    expect(screen.getByText("Comparable")).toBeTruthy();
    expect(screen.getByText("Medium")).toBeTruthy();
    expect(screen.getByText("Observing")).toBeTruthy();
    expect(screen.getByText("Increasing")).toBeTruthy();
    expect(screen.queryByText("Limited · 0%")).toBeNull();
    expect(screen.queryByText("Limited confidence")).toBeNull();
  });

  it("renders a historical low operating-context dimension as a factual comparability status", () => {
    render(React.createElement(FindingClassificationSummary, {
      finding: {
        classification: { type: "context_limited_relationship_change", confidence: "limited" },
        confidenceDimensions: {
          changeDetection: { level: "high" },
          interpretation: { level: "low", attribution_status: "unattributed" },
          operatingContext: { level: "low" },
          evidenceQuality: { level: "high" },
        },
      },
    }));

    expect(screen.getByText("Different From Baseline")).toBeTruthy();
    expect(screen.queryByText("Cause")).toBeNull();
    expect(screen.getByTestId("finding-classification-summary").getAttribute("aria-label")).not.toMatch(/cause|diagnosis/i);
    expect(screen.queryByText("Low · Unattributed")).toBeNull();
  });
});
