import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
    Panel: ({ title, subtitle, children, className = "" }) => (
      <section className={className}>
        <h2>{title}</h2>
        {subtitle ? <p>{subtitle}</p> : null}
        {children}
      </section>
    ),
    MetricGrid: ({ metrics = [] }) => (
      <dl>
        {metrics.map((metric) => (
          <div key={metric.label}>
            <dt>{metric.label}</dt>
            <dd>{metric.value}</dd>
          </div>
        ))}
      </dl>
    ),
    hasActiveSession: true,
    hasRealSiiOutput: true,
    currentSession: { jobId: "job-1", hasReliableOperatorEvidence: true },
    ...overrides,
  };
}

function renderReplayWorkspace(props = baseProps()) {
  return render(<ReplayWorkspace {...props} />);
}

function expectFrame(text) {
  expect(screen.getByText(text)).toBeTruthy();
}

function clickNamedButton(name) {
  fireEvent.click(screen.getAllByRole("button", { name })[0]);
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("ReplayWorkspace playback stability", () => {
  it("play advances monotonically and stops at final frame", async () => {
    renderReplayWorkspace(baseProps());

    await waitFor(() => expectFrame("1/4"));
    fireEvent.change(screen.getAllByDisplayValue("1x")[0], { target: { value: "4" } });

    clickNamedButton("Play");

    await waitFor(() => expectFrame("4/4"), { timeout: 4000 });
    await waitFor(() => expect(screen.getAllByRole("button", { name: "Play" })[0]).toBeTruthy());

    expectFrame("4/4");
  });

  it("keeps technical replay diagnostics out of the default view", async () => {
    renderReplayWorkspace(baseProps());

    await waitFor(() => expectFrame("1/4"));
    expect(screen.getByText("Current Status")).toBeTruthy();
    expect(screen.getByText("Supporting Evidence")).toBeTruthy();
    expect(screen.getByText("Review next")).toBeTruthy();
    expect(screen.queryByText("Raw change direction")).toBeNull();
    expect(screen.queryByText("Structural Progression")).toBeNull();
  });

  it("manual next and previous move exactly one frame", async () => {
    renderReplayWorkspace(baseProps());

    await waitFor(() => expectFrame("1/4"));

    clickNamedButton("Next");
    expectFrame("2/4");

    clickNamedButton("Previous");
    expectFrame("1/4");
  });
});
