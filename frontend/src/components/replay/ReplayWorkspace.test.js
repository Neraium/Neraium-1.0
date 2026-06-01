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

function renderReplayWorkspace(props) {
  return render(h(ReplayWorkspace, props));
}

function baseProps({ apiFetch, currentSession } = {}) {
  const fetchMock = apiFetch ?? vi.fn(async (path) => {
    if (String(path).startsWith("/api/replay/timeline")) {
      return createResponse({ timeline: buildFrames(4), meta: { frame_count: 4 } });
    }
    return createResponse({}, 404);
  });

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
    const fetchMock = vi.fn(async (path) => {
      if (String(path).startsWith("/api/replay/timeline")) {
        return createResponse({ timeline: buildFrames(4), meta: { frame_count: 4 } });
      }
      return createResponse({}, 404);
    });

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
    const fetchMock = vi.fn(async (path) => {
      if (String(path).startsWith("/api/replay/timeline")) {
        return createResponse({ timeline: buildFrames(4), meta: { frame_count: 4 } });
      }
      return createResponse({}, 404);
    });

    const { rerender } = renderReplayWorkspace(baseProps({ apiFetch: fetchMock, currentSession: { latestUploadResult: { job_id: "job-1" }, latestUploadSnapshot: null } }));
    await waitFor(() => expectFrame("1/4"));

    clickNamedButton("Next");
    expectFrame("2/4");

    rerender(h(ReplayWorkspace, baseProps({ apiFetch: fetchMock, currentSession: { latestUploadResult: { job_id: "job-2" }, latestUploadSnapshot: null } })));

    await waitFor(() => expectFrame("1/4"));
  });
});
