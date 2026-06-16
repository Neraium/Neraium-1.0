/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ReplayWorkspace from "./ReplayWorkspace";

const h = React.createElement;

vi.mock("../PropagationMap", () => ({ default: () => h("div", { "data-testid": "propagation-map" }) }));
vi.mock("../StructuralMemoryPanel", () => ({ default: () => h("div", { "data-testid": "structural-memory" }) }));
vi.mock("../EvidenceLineagePanel", () => ({ default: () => h("div", { "data-testid": "evidence-lineage" }) }));
vi.mock("../EvidenceInteractionPanel", () => ({ default: () => h("div", { "data-testid": "evidence-interaction" }) }));
vi.mock("../ReplayCognitionField", () => ({ default: () => h("div", { "data-testid": "replay-cognition" }) }));

function createResponse(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  };
}

function buildFrames(count = 4) {
  return Array.from({ length: count }, (_, i) => ({
    frame_number: i,
    timestamp_start: `2026-01-01T00:00:0${i}Z`,
    timestamp_end: `2026-01-01T00:00:0${i}Z`,
    status: "ACTIVE",
  }));
}

function createReplayApiFetch(frameCount = 4) {
  return vi.fn(async (path) => {
    if (String(path).startsWith("/api/data/upload-status/")) {
      return createResponse({ status: "COMPLETE", replay_ready: true, result_available: true });
    }
    if (String(path).startsWith("/api/data/replay/")) {
      return createResponse({ timeline: buildFrames(frameCount), meta: { frame_count: frameCount } });
    }
    if (String(path) === "/api/evidence/runs") return createResponse({ runs: [] });
    return createResponse({}, 404);
  });
}

function renderReplayWorkspace(props) {
  return render(h(ReplayWorkspace, props));
}

function baseProps({ apiFetch, currentSession } = {}) {
  const fetchMock = apiFetch ?? createReplayApiFetch();

  return {
    apiFetch: fetchMock,
    accessCode: "",
    normalizeErrorMessage: (v) => String(v ?? ""),
    formatClockTime: (value) => String(value ?? ""),
    Panel: ({ children }) => h("div", null, children),
    MetricGrid: () => h("div"),
    currentSession: currentSession ?? { latestUploadResult: { job_id: "job-1" }, latestUploadSnapshot: null },
    hasActiveSession: true,
  };
}

function expectFrame(label) {
  expect(screen.getByText(new RegExp(`Frame ${label}`))).toBeTruthy();
}

function clickNamedButton(name, index = 0) {
  fireEvent.click(screen.getAllByRole("button", { name })[index]);
}

afterEach(() => {
  cleanup();
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

    await waitFor(() => expectFrame("1\/4"));
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

  it("slider selection persists", async () => {
    renderReplayWorkspace(baseProps());

    await waitFor(() => expectFrame("1/4"));

    const slider = screen.getAllByRole("slider")[0];
    fireEvent.change(slider, { target: { value: "2" } });
    expectFrame("3/4");

    await new Promise((resolve) => setTimeout(resolve, 600));
    expectFrame("3/4");
  });

  it("timeline refetch with same session does not reset current frame", async () => {
    const fetchMock = createReplayApiFetch();

    const props = baseProps({ apiFetch: fetchMock, currentSession: { latestUploadResult: { job_id: "job-1" }, latestUploadSnapshot: null } });
    const { rerender } = renderReplayWorkspace(props);

    await waitFor(() => expectFrame("1/4"));
    clickNamedButton("Next");
    expectFrame("2/4");

    const nextProps = baseProps({
      apiFetch: fetchMock,
      currentSession: {
        latestUploadResult: { job_id: "job-1", replay_timeline: { timeline: [...buildFrames(4)] } },
        latestUploadSnapshot: null,
      },
    });
    rerender(h(ReplayWorkspace, nextProps));

    await waitFor(() => expectFrame("2/4"));
  });

  it("new replay session resets frame index", async () => {
    const fetchMock = createReplayApiFetch();

    const { rerender } = renderReplayWorkspace(baseProps({ apiFetch: fetchMock, currentSession: { latestUploadResult: { job_id: "job-1" }, latestUploadSnapshot: null } }));
    await waitFor(() => expectFrame("1/4"));

    clickNamedButton("Next");
    expectFrame("2/4");

    rerender(h(ReplayWorkspace, baseProps({ apiFetch: fetchMock, currentSession: { latestUploadResult: { job_id: "job-2" }, latestUploadSnapshot: null } })));

    await waitFor(() => expectFrame("1/4"));
  });

  it("keeps Supporting Evidence empty when no persisted evidence run exists", async () => {
    renderReplayWorkspace(baseProps({ currentSession: { latestUploadResult: { job_id: "job-1" } } }));

    await waitFor(() => expectFrame("1/4"));
    expect(screen.getByLabelText("Supporting evidence").querySelectorAll("li")).toHaveLength(0);
  });

  it("renders telemetry-derived evidence for the matching persisted upload run", async () => {
    const fetchMock = vi.fn(async (path) => {
      if (String(path).startsWith("/api/data/upload-status/job-real")) {
        return createResponse({ status: "COMPLETE", replay_ready: true, result_available: true });
      }
      if (String(path).startsWith("/api/data/replay/job-real")) {
        return createResponse({
          job_id: "job-real",
          run_id: "job-real",
          upload_id: "job-real",
          timeline: [{
            ...buildFrames(1)[0],
            primary_contributors: ["temperature", "humidity"],
            cognition_state: { confidence_tier: "relationship_evidence_present" },
            topology_state: { drift_index: 0.73, stability_state: "Needs review" },
          }],
          meta: { frame_count: 1, job_id: "job-real", lineage: { aligned: true, job_id: "job-real", run_id: "job-real", upload_id: "job-real" } },
        });
      }
      if (String(path) === "/api/evidence/runs") {
        return createResponse({
          runs: [{
            run_id: "job-real",
            status: "completed",
            source_name: "uploaded-telemetry.csv",
            variables: ["temperature", "humidity"],
            evidence_summary: ["Temperature and humidity coupling moved away from baseline."],
            drift_metrics: { baseline_distance: null, drift_index: 0.73, confidence: 0.88 },
            deformation_started_at: "2026-01-01T00:00:00Z",
          }],
        });
      }
      return createResponse({}, 404);
    });

    renderReplayWorkspace({
      ...baseProps({
        apiFetch: fetchMock,
        currentSession: {
          latestUploadResult: {
            job_id: "job-real",
            filename: "uploaded-telemetry.csv",
            sii_intelligence: { source: "uploaded" },
          },
        },
      }),
      hasRealSiiOutput: true,
    });

    await waitFor(() => expect(screen.getByText("Source file: uploaded-telemetry.csv")).toBeTruthy());
    expect(screen.getByText("Run ID: job-real")).toBeTruthy();
    expect(screen.getByText("Variables: temperature | humidity")).toBeTruthy();
    expect(screen.getByText("Relationship summary: Temperature and humidity coupling moved away from baseline.")).toBeTruthy();
    expect(screen.getByText("Change metric: 0.73")).toBeTruthy();
    expect(screen.getByText("Confidence: 88%")).toBeTruthy();
  });

  it("prefers job-scoped replay and does not use global replay as production evidence", async () => {
    const fetchMock = vi.fn(async (path) => {
      if (String(path).startsWith("/api/data/upload-status/job-scoped")) {
        return createResponse({ status: "COMPLETE", replay_ready: true, result_available: true });
      }
      if (String(path).startsWith("/api/data/replay/job-scoped")) {
        return createResponse({ timeline: buildFrames(2), meta: { frame_count: 2, job_id: "job-scoped" } });
      }
      if (String(path) === "/api/evidence/runs") return createResponse({ runs: [] });
      if (String(path).startsWith("/api/replay/timeline")) {
        return createResponse({ timeline: buildFrames(9), meta: { frame_count: 9 } });
      }
      return createResponse({}, 404);
    });

    renderReplayWorkspace({
      ...baseProps({ apiFetch: fetchMock, currentSession: { latestUploadResult: { job_id: "job-scoped" } } }),
      hasRealSiiOutput: true,
    });

    await waitFor(() => expectFrame("1/2"));
    expect(fetchMock.mock.calls.some(([path]) => String(path).startsWith("/api/data/replay/job-scoped"))).toBe(true);
    expect(fetchMock.mock.calls.some(([path]) => String(path).startsWith("/api/replay/timeline"))).toBe(false);
    expect(screen.getByLabelText("Supporting evidence").querySelectorAll("li")).toHaveLength(0);
  });
});

  it("does not fetch replay from stale history when there is no current upload", async () => {
    const fetchMock = vi.fn(async (path) => {
      if (String(path) === "/api/data/latest-upload?include_persisted=1") {
        return createResponse({ latest_result: null, history: [{ job_id: "stale-history-job" }] });
      }
      if (String(path) === "/api/evidence/runs") return createResponse({ runs: [] });
      return createResponse({}, 404);
    });

    renderReplayWorkspace({
      ...baseProps({ apiFetch: fetchMock, currentSession: { latestUploadResult: null, latestUploadSnapshot: null } }),
      hasRealSiiOutput: true,
    });

    await waitFor(() => expect(screen.getByText("No replay is available for the active session.")).toBeTruthy());
    expect(fetchMock.mock.calls.some(([path]) => String(path).includes("stale-history-job"))).toBe(false);
  });
