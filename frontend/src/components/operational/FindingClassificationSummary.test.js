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

    expect(screen.getByText("Not established")).toBeTruthy();
    expect(screen.getByText("Evidence trend")).toBeTruthy();
    expect(screen.queryByText("81 days")).toBeNull();
    expect(screen.queryByText(/^Trajectory$/)).toBeNull();
  });
});
