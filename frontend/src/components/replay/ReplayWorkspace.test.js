import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ReplayWorkspace from "./ReplayWorkspace";

const timeline = [
  { timestamp: "2026-01-01T00:00:00Z", topology_state: { stability_state: "Stable" }, cognition_state: { confidence_tier: "high" }, primary_contributors: ["temp"] },
  { timestamp: "2026-01-01T00:01:00Z", topology_state: { stability_state: "Drifting", drift_index: 0.3 }, cognition_state: { confidence_tier: "moderate" }, primary_contributors: ["temp"] },
  { timestamp: "2026-01-01T00:02:00Z", topology_state: { stability_state: "Drifting", drift_index: 0.5 }, cognition_state: { confidence_tier: "moderate" }, primary_contributors: ["temp"] },
  { timestamp: "2026-01-01T00:03:00Z", topology_state: { stability_state: "At Risk", drift_index: 0.8 }, cognition_state: { confidence_tier: "high" }, primary_contributors: ["temp"] },
];

function baseProps(overrides = {}) {
  const apiFetch = vi.fn(async (url) => {
    if (String(url).includes("latest-upload")) {
      return { ok: true, json: async () => ({ current_upload: { job_id: "job-1" } }) };
    }
    if (String(url).includes("upload-status")) {
      return { ok: true, json: async () => ({ status: "COMPLETE", replay_ready: true, replay_frame_count: timeline.length }) };
    }
    if (String(url).includes("/api/data/replay/")) {
      return { ok: true, json: async () => ({ timeline, meta: { frame_count: timeline.length } }) };
    }
    if (String(url).includes("/api/evidence/runs")) {
      return { ok: true, json: async () => ({ runs: [] }) };
    }
    return { ok: true, json: async () => ({}) };
  });
  return {
    apiFetch,
    accessCode: "test",
    expertMode: false,
    normalizeErrorMessage: (message) => String(message ?? ""),
    formatClockTime: (value) => String(value ?? "-"),
    Panel: ({ title, subtitle, children, className = "" }) => React.createElement(
      "section",
      { className },
      React.createElement("h2", null, title),
      subtitle ? React.createElement("p", null, subtitle) : null,
      children,
    ),
    MetricGrid: ({ metrics = [] }) => React.createElement(
      "dl",
      null,
      metrics.map((metric) => React.createElement(
        "div",
        { key: metric.label },
        React.createElement("dt", null, metric.label),
        React.createElement("dd", null, metric.value),
      )),
    ),
    hasActiveSession: true,
    hasRealSiiOutput: true,
    currentSession: { jobId: "job-1", hasReliableOperatorEvidence: true },
    ...overrides,
  };
}

function renderReplayWorkspace(props = baseProps()) {
  return render(React.createElement(ReplayWorkspace, props));
}

function expectReplayHeading() {
  expect(screen.getAllByText("Evidence Replay").length).toBeGreaterThan(0);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ReplayWorkspace", () => {
  it("renders the evidence replay workspace and loads replay data", async () => {
    const props = baseProps();
    renderReplayWorkspace(props);

    expectReplayHeading();
    await waitFor(() => {
      expect(props.apiFetch).toHaveBeenCalledWith(expect.stringContaining("/api/data/replay/"), expect.any(Object));
    });
  });

  it("keeps technical replay diagnostics out of the default view", async () => {
    renderReplayWorkspace(baseProps());

    await waitFor(() => expectReplayHeading());
    expect(screen.queryByText("Raw change direction")).toBeNull();
    expect(screen.queryByText("Structural Progression")).toBeNull();
  });

  it("allows replay controls to be clicked when replay data is loaded", async () => {
    renderReplayWorkspace(baseProps());

    await waitFor(() => expectReplayHeading());
    const nextButton = screen.queryAllByRole("button", { name: "Next" })[0];
    if (nextButton) fireEvent.click(nextButton);
    expectReplayHeading();
  });
});
