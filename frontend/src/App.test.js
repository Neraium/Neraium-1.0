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
const runtimeState = vi.hoisted(() => ({
  latestUploadResult: null,
  latestUploadSnapshot: { status: "empty" },
}));

vi.mock("./config", () => ({
  apiFetch: vi.fn(async () => ({ ok: true, json: async () => ({}) })),
  ENABLE_ADMISSION_GATE: false,
}));

vi.mock("./services/api/authApi", () => ({
  fetchCurrentUser: vi.fn().mockResolvedValue({ authenticated: true, user: { email: "operator@facility.com", name: "Operator", role: "operator" } }),
  loginUser: vi.fn().mockResolvedValue({ authenticated: true, user: { email: "operator@facility.com", name: "Operator", role: "operator" } }),
  logoutUser: vi.fn().mockResolvedValue({ authenticated: false }),
}));

vi.mock("./hooks/useFacilityRuntime", () => ({
  default: () => ({
    apiStatus: { state: "online" },
    systems: [],
    systemsState: "ready",
    intelligenceStatus: {},
    latestUploadResult: runtimeState.latestUploadResult,
    latestUploadSnapshot: runtimeState.latestUploadSnapshot,
    domainDetection: null,
    allowPersistedLatest: true,
    telemetryTick: 0,
    domainMode: "aquatic",
    ...runtimeMocks,
  }),
}));

vi.mock("./components/MonitoringWorkspace", () => ({
  default: ({ activeWorkspace, liveOps, pendingUploadFiles = [], onWorkspaceNavigate, onSignOut }) => h(
    "div",
    { "data-testid": "monitoring-workspace-mock" },
    h("span", { "data-testid": "active-workspace" }, activeWorkspace),
    h("span", { "data-testid": "active-result" }, liveOps.latestUploadResult?.job_id ?? "empty"),
    h("span", { "data-testid": "pending-file-count" }, String(pendingUploadFiles.length)),
    h("button", { type: "button", onClick: () => onWorkspaceNavigate("data") }, "Open Data"),
    h("button", { type: "button", onClick: () => onWorkspaceNavigate("findings") }, "Open Findings"),
    h("button", { type: "button", onClick: onSignOut }, "Sign out"),
  ),
}));

beforeEach(() => {
  window.history.replaceState({}, "", "/");
  window.localStorage.clear();
  window.sessionStorage.clear();
  runtimeState.latestUploadResult = null;
  runtimeState.latestUploadSnapshot = { status: "empty" };
  Object.values(runtimeMocks).forEach((mock) => mock.mockClear());
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function renderApp() {
  render(h(App));
  return screen.findByTestId("monitoring-workspace-mock");
}

describe("App monitoring routes", () => {
  it("opens Status directly at the root without a report or landing step", async () => {
    await renderApp();
    expect(screen.getByTestId("active-workspace").textContent).toBe("status");
    expect(window.location.pathname).toBe("/");
  });

  it.each([
    ["/status", "status"],
    ["/findings", "findings"],
    ["/findings/run-42", "evidence"],
    ["/systems", "systems"],
    ["/data", "data"],
  ])("supports direct URL navigation for %s", async (path, workspace) => {
    window.history.replaceState({}, "", path);
    await renderApp();
    expect(screen.getByTestId("active-workspace").textContent).toBe(workspace);
  });

  it.each([
    ["/portfolio", "status"],
    ["/workspace", "status"],
    ["/workspace/insights", "findings"],
    ["/workspace/data-sources", "data"],
    ["/evidence/legacy-run", "evidence"],
  ])("maps old direct URLs to the compatible monitoring route %s", async (path, workspace) => {
    window.history.replaceState({}, "", path);
    await renderApp();
    expect(screen.getByTestId("active-workspace").textContent).toBe(workspace);
  });

  it("updates browser history when primary navigation changes", async () => {
    await renderApp();
    fireEvent.click(screen.getByRole("button", { name: "Open Data" }));
    expect(screen.getByTestId("active-workspace").textContent).toBe("data");
    expect(window.location.pathname).toBe("/data");
    fireEvent.click(screen.getByRole("button", { name: "Open Findings" }));
    expect(screen.getByTestId("active-workspace").textContent).toBe("findings");
    expect(window.location.pathname).toBe("/findings");
  });

  it("uses backend-owned current state instead of restoring stale local analysis", async () => {
    window.localStorage.setItem("neraium.completed_analysis_history", JSON.stringify([{ id: "stale", result: { job_id: "stale-job" } }]));
    await renderApp();
    expect(screen.getByTestId("active-result").textContent).toBe("empty");
  });

  it("passes a persisted current backend result into monitoring", async () => {
    runtimeState.latestUploadResult = { job_id: "persisted-current", status: "complete", sii_completed: true, row_count: 100, sii_intelligence: { facility_state: "Monitoring" } };
    runtimeState.latestUploadSnapshot = { status: "complete", current_upload: { job_id: "persisted-current" } };
    await renderApp();
    expect(screen.getByTestId("active-result").textContent).toBe("persisted-current");
  });

  it("clears dataset state when the authenticated session expires", async () => {
    await renderApp();
    window.dispatchEvent(new CustomEvent("neraium:session-expired"));
    expect(await screen.findByTestId("auth-screen")).toBeTruthy();
    expect(runtimeMocks.clearUploadSessionState).toHaveBeenCalled();
  });

  it("signs out without carrying dataset state into the next session", async () => {
    await renderApp();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(screen.getByTestId("auth-screen")).toBeTruthy());
    expect(runtimeMocks.clearUploadSessionState).toHaveBeenCalled();
  });
});
