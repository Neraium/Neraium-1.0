/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const h = React.createElement;
const runtimeMocks = vi.hoisted(() => ({
  loadFacilitySystems: vi.fn(async () => true),
  loadLatestUploadState: vi.fn(async () => true),
  setAllowPersistedLatest: vi.fn(),
  setIsDemoMode: vi.fn(),
  clearUploadSessionState: vi.fn(),
}));

vi.mock("./config", () => ({
  apiFetch: vi.fn(),
  ENABLE_ADMISSION_GATE: false,
}));

vi.mock("./services/api/authApi", () => ({ logoutUser: vi.fn() }));

vi.mock("./hooks/useFacilityRuntime", () => ({
  default: () => ({
    apiStatus: { state: "online" },
    systems: [],
    systemsState: "ready",
    intelligenceStatus: {},
    latestUploadResult: null,
    latestUploadSnapshot: { status: "empty" },
    domainDetection: null,
    allowPersistedLatest: true,
    telemetryTick: 0,
    domainMode: "aquatic",
    ...runtimeMocks,
  }),
}));

vi.mock("./components/SystemTopologyWorkspace", () => ({
  default: ({ liveOps, onWorkspaceNavigate }) => h(
    "div",
    { "data-testid": "gate-workspace" },
    h("span", { "data-testid": "gate-result" }, liveOps.latestUploadResult?.job_id ?? "empty"),
    h("button", { type: "button", onClick: () => onWorkspaceNavigate("data-connections") }, "Open uploads"),
  ),
}));

vi.mock("./components/DataConnectionsWorkspace", () => ({
  default: ({ onUploadComplete }) => h(
    "div",
    { "data-testid": "upload-workspace" },
    h("button", {
      type: "button",
      onClick: () => onUploadComplete({
        status: "complete",
        latest_result: {
          job_id: "persisted-job-42",
          sii_intelligence: { facility_state: "Monitoring" },
        },
      }),
    }, "Finish upload"),
    h("button", {
      type: "button",
      onClick: () => onUploadComplete({
        latest_result: { job_id: "restored-job-7", sii_intelligence: { facility_state: "Monitoring" } },
      }, { navigateToGate: false }),
    }, "Restore upload"),
  ),
}));

beforeEach(() => {
  window.localStorage.clear();
  Object.values(runtimeMocks).forEach((mock) => mock.mockClear());
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("App upload completion navigation", () => {
  it("refreshes persisted upload state and returns to the Gate", async () => {
    render(h(App));

    fireEvent.click(screen.getByRole("button", { name: "Open uploads" }));
    expect(screen.getByTestId("upload-workspace")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Finish upload" }));

    await waitFor(() => {
      expect(screen.getByTestId("gate-workspace")).toBeTruthy();
    });

    expect(screen.getByTestId("gate-result").textContent).toBe("persisted-job-42");
    expect(runtimeMocks.loadLatestUploadState).toHaveBeenCalledWith({ includePersisted: true });
    expect(runtimeMocks.loadFacilitySystems).toHaveBeenCalledTimes(1);
  });

  it("does not leave Data Connections when an existing upload is restored", async () => {
    render(h(App));

    fireEvent.click(screen.getByRole("button", { name: "Open uploads" }));
    fireEvent.click(screen.getByRole("button", { name: "Restore upload" }));

    await waitFor(() => {
      expect(runtimeMocks.loadLatestUploadState).toHaveBeenCalledWith({ includePersisted: true });
    });

    expect(screen.getByTestId("upload-workspace")).toBeTruthy();
    expect(screen.queryByTestId("gate-workspace")).toBeNull();
  });
});
