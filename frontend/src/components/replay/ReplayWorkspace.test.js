/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ReplayWorkspace from "./ReplayWorkspace";

const h = React.createElement;

function createResponse(payload, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

function buildFrames(count = 4) {
  return Array.from({ length: count }, (_, i) => ({
    frame_number: i,
    timestamp_start: `2026-01-01T00:0${i}:00Z`,
    timestamp_end: `2026-01-01T00:0${i}:00Z`,
    baseline_distance: i / Math.max(count, 1),
    primary_contributors: ["flow_gpm", "pump_speed_pct"],
    topology_state: { stability_state: i === 0 ? "stable" : "needs review", drift_index: i / Math.max(count, 1) },
  }));
}

function createStoryApiFetch(frameCount = 4) {
  return vi.fn(async (path) => {
    if (String(path).startsWith("/api/data/upload-status/")) return createResponse({ status: "COMPLETE", replay_ready: true, result_available: true });
    if (String(path).startsWith("/api/data/replay/")) return createResponse({ timeline: buildFrames(frameCount), meta: { frame_count: frameCount } });
    if (String(path) === "/api/evidence/runs") return createResponse({ runs: [] });
    return createResponse({}, 404);
  });
}

function baseProps({ apiFetch, currentSession } = {}) {
  const defaultSession = {
    latestUploadResult: { job_id: "job-1" },
    latestUploadSnapshot: null,
    hasReliableOperatorEvidence: true,
    reviewReadiness: "ready",
  };
  return {
    apiFetch: apiFetch ?? createStoryApiFetch(),
    accessCode: "",
    normalizeErrorMessage: (value) => String(value ?? ""),
    formatClockTime: (value) => String(value ?? ""),
    Panel: ({ title, children }) => h("section", { "aria-label": title }, children),
    currentSession: currentSession ? { ...defaultSession, ...currentSession } : defaultSession,
    hasActiveSession: true,
  };
}

function renderStory(props) {
  return render(h(ReplayWorkspace, props));
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("System Story workspace", () => {
  it("renders the flagship story sections without internal graph diagnostics", async () => {
    renderStory(baseProps());

    await waitFor(() => expect(screen.getByText("System Story")).toBeTruthy());
    expect(screen.getByLabelText("Why We Believe It")).toBeTruthy();
    expect(screen.getByLabelText("Likely Causes")).toBeTruthy();
    expect(screen.getByLabelText("What To Inspect")).toBeTruthy();
    expect(screen.getByLabelText("How It Developed")).toBeTruthy();
    expect(screen.getByLabelText("Supporting Trends")).toBeTruthy();
    expect(screen.getByLabelText("Engineer Notes")).toBeTruthy();
    expect(screen.getByLabelText("Repair Outcome")).toBeTruthy();
    expect(screen.queryByTestId("propagation-map")).toBeNull();
    expect(screen.queryByText("Raw change direction")).toBeNull();
  });

  it("uses the story timeline slider without playback controls", async () => {
    renderStory(baseProps());

    await waitFor(() => expect(screen.getByDisplayValue("3")).toBeTruthy());
    const slider = screen.getByRole("slider", { name: "Story timeline" });
    fireEvent.change(slider, { target: { value: "1" } });

    expect(screen.getByDisplayValue("1")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Play" })).toBeNull();
  });

  it("starts a new story session at the latest point", async () => {
    const fetchMock = createStoryApiFetch();
    const { rerender } = renderStory(baseProps({ apiFetch: fetchMock, currentSession: { latestUploadResult: { job_id: "job-1" } } }));

    await waitFor(() => expect(screen.getByDisplayValue("3")).toBeTruthy());
    fireEvent.change(screen.getByRole("slider", { name: "Story timeline" }), { target: { value: "1" } });
    expect(screen.getByDisplayValue("1")).toBeTruthy();

    rerender(h(ReplayWorkspace, baseProps({ apiFetch: fetchMock, currentSession: { latestUploadResult: { job_id: "job-2" } } })));
    await waitFor(() => expect(screen.getByDisplayValue("3")).toBeTruthy());
  });

  it("renders telemetry-derived evidence in plain English", async () => {
    const fetchMock = vi.fn(async (path) => {
      if (String(path).startsWith("/api/data/upload-status/job-real")) return createResponse({ status: "COMPLETE", replay_ready: true, result_available: true });
      if (String(path).startsWith("/api/data/replay/job-real")) {
        return createResponse({ timeline: [{ ...buildFrames(1)[0], primary_contributors: ["temperature", "humidity"], topology_state: { drift_index: 0.73, stability_state: "Needs review" } }], meta: { frame_count: 1 } });
      }
      if (String(path) === "/api/evidence/runs") {
        return createResponse({ runs: [{ run_id: "job-real", status: "completed", variables: ["temperature", "humidity"], evidence_summary: ["Temperature and humidity relationship divergence moved away from State Group A with replay/relationship evidence."], deformation_started_at: "2026-01-01T00:00:00Z" }] });
      }
      return createResponse({}, 404);
    });

    renderStory(baseProps({ apiFetch: fetchMock, currentSession: { latestUploadResult: { job_id: "job-real" } } }));

    await waitFor(() => expect(screen.getByText(/Temperature and humidity system behavior changed/i)).toBeTruthy());
    expect(screen.queryByText(/relationship divergence/i)).toBeNull();
    expect(screen.queryByText(/State Group A/i)).toBeNull();
    expect(screen.getByText("Sensor drift")).toBeTruthy();
  });

  it("prefers the job-scoped story source", async () => {
    const fetchMock = vi.fn(async (path) => {
      if (String(path).startsWith("/api/data/upload-status/job-scoped")) return createResponse({ status: "COMPLETE", replay_ready: true, result_available: true });
      if (String(path).startsWith("/api/data/replay/job-scoped")) return createResponse({ timeline: buildFrames(2), meta: { frame_count: 2 } });
      if (String(path) === "/api/evidence/runs") return createResponse({ runs: [] });
      if (String(path).startsWith("/api/replay/timeline")) return createResponse({ timeline: buildFrames(9) });
      return createResponse({}, 404);
    });

    renderStory(baseProps({ apiFetch: fetchMock, currentSession: { latestUploadResult: { job_id: "job-scoped" } } }));

    await waitFor(() => expect(screen.getByText("2 observation points")).toBeTruthy());
    expect(fetchMock.mock.calls.some(([path]) => String(path).startsWith("/api/data/replay/job-scoped"))).toBe(true);
    expect(fetchMock.mock.calls.some(([path]) => String(path).startsWith("/api/replay/timeline"))).toBe(false);
  });

  it("shows pending verification in story language", async () => {
    renderStory(baseProps({
      apiFetch: createStoryApiFetch(2),
      currentSession: { latestUploadResult: { job_id: "job-pending" }, hasReliableOperatorEvidence: false, reviewReadiness: "quality_gate" },
    }));

    await waitFor(() => expect(screen.getByText("Telemetry is present, but the story is waiting for verification.")).toBeTruthy());
    expect(screen.getAllByText(/does not yet meet the reliability threshold/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/stable telemetry|data quality|processing/i).length).toBeGreaterThan(0);
  });

  it("records engineer notes and repair outcome labels", async () => {
    renderStory(baseProps());

    await waitFor(() => expect(screen.getByLabelText("Engineer Notes")).toBeTruthy());
    fireEvent.change(screen.getByPlaceholderText("Add inspection notes"), { target: { value: "Valve replaced." } });
    fireEvent.click(screen.getByRole("button", { name: "Add Note" }));
    fireEvent.click(screen.getByRole("button", { name: "Maintenance event" }));

    expect(screen.getAllByText("Valve replaced.").length).toBeGreaterThan(1);
    expect(screen.getByText(/Marked as maintenance event/i)).toBeTruthy();
  });

  it("does not fetch stale history when there is no current upload", async () => {
    const fetchMock = vi.fn(async (path) => {
      if (String(path) === "/api/data/latest-upload?include_persisted=1") return createResponse({ latest_result: null, history: [{ job_id: "stale-history-job" }] });
      if (String(path) === "/api/evidence/runs") return createResponse({ runs: [] });
      return createResponse({}, 404);
    });

    renderStory(baseProps({ apiFetch: fetchMock, currentSession: { latestUploadResult: null, latestUploadSnapshot: null } }));

    await waitFor(() => expect(screen.getByText("System Story is waiting for an active telemetry session.")).toBeTruthy());
    expect(fetchMock.mock.calls.some(([path]) => String(path).includes("stale-history-job"))).toBe(false);
  });
});