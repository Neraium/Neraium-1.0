/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ObservationCenterWorkspace from "./ObservationCenterWorkspace";

const h = React.createElement;

vi.mock("./workspacePrimitives", () => ({
  EmptyState: ({ title, body }) => h("div", { "data-testid": "empty-state" }, h("strong", null, title), h("p", null, body)),
  MetricGrid: ({ metrics }) => h("div", { "data-testid": "metric-grid" }, metrics?.map((metric) => h("div", { key: metric.label }, `${metric.label}:${metric.value}`))),
  Panel: ({ title, children }) => h("section", { "data-testid": title }, h("h2", null, title), children),
}));

vi.mock("./SystemStateMark", () => ({ default: () => h("div", { "data-testid": "system-state-mark" }) }));

function createResponse(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  };
}

function installLocalStorageMock() {
  const store = new Map();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => {
        store.set(String(key), String(value));
      },
      removeItem: (key) => {
        store.delete(String(key));
      },
      clear: () => {
        store.clear();
      },
    },
  });
}

function renderWorkspace({ apiFetch = vi.fn(async () => createResponse({ runs: [] })), canonicalFinding, currentSession, onReviewEvidence = vi.fn() } = {}) {
  return render(h(ObservationCenterWorkspace, { apiFetch, accessCode: "", canonicalFinding, currentSession, onReviewEvidence }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ObservationCenterWorkspace", () => {
  it("renders the canonical empty state consistently", async () => {
    installLocalStorageMock();
    renderWorkspace({
      canonicalFinding: {
        exists: false,
        status: "Normal",
        confidence: "Low",
        summary: "No current observations.",
        whyItMatters: "Telemetry is being monitored.",
        reviewNext: "No structural changes detected.",
        supportingEvidence: [],
        technicalDetails: [],
        dataQuality: { missingBaselineValues: [], missingRecentValues: [], unavailableTelemetry: [] },
        evidenceButtonLabel: "Review Details",
        emptyState: {
          title: "No current observations.",
          subtitle: "Telemetry is being monitored.",
          detail: "No structural changes detected.",
        },
      },
    });

    await waitFor(() => expect(screen.getAllByText("No current observations.").length).toBeGreaterThan(0));
    expect(screen.getAllByText("Telemetry is being monitored.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("No structural changes detected.").length).toBeGreaterThan(0);
  });

  it("renders the canonical finding summary and opens evidence review", async () => {
    installLocalStorageMock();
    const onReviewEvidence = vi.fn();
    renderWorkspace({
      canonicalFinding: {
        exists: true,
        status: "Behavior Change Detected",
        confidence: "Moderate",
        summary: "System behavior has moved away from its historical operating pattern.",
        whyItMatters: "The observed relationships between system variables have changed.",
        reviewNext: "Review supporting evidence.",
        supportingEvidence: ["Affected variables: temperature, humidity."],
        technicalDetails: [{ label: "Drift magnitude", value: "0.70" }],
        dataQuality: { missingBaselineValues: [], missingRecentValues: ["Missing values in recent telemetry."], unavailableTelemetry: [] },
        evidenceButtonLabel: "Review Details",
        historicalComparison: "Historical comparison evidence supports a change from the normal pattern.",
        emptyState: {
          title: "No current observations.",
          subtitle: "Telemetry is being monitored.",
          detail: "No structural changes detected.",
        },
      },
      onReviewEvidence,
    });

    await waitFor(() => expect(screen.getAllByText("Behavior Change Detected").length).toBeGreaterThan(0));
    expect(screen.getAllByText("System behavior has moved away from its historical operating pattern.").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Confidence:Moderate/i).length).toBeGreaterThan(0);
    expect(screen.getByText("Filter issues")).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Review Details" })[0]);
    expect(onReviewEvidence).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/State Group A/i)).toBeNull();
    expect(screen.queryByText(/relationship divergence/i)).toBeNull();
  });

  it("synthesizes the current review item from the canonical finding when no evidence run is persisted yet", async () => {
    installLocalStorageMock();
    renderWorkspace({
      canonicalFinding: {
        exists: true,
        runId: "job-current-1",
        status: "Behavior Change Detected",
        confidence: "Moderate",
        summary: "System behavior has moved away from its historical operating pattern.",
        whyItMatters: "The observed relationships between system variables have changed.",
        reviewNext: "Review supporting evidence.",
        supportingEvidence: ["Affected variables: temperature, humidity."],
        technicalDetails: [{ label: "Behavior duration", value: "4h" }],
        dataQuality: { missingBaselineValues: [], missingRecentValues: [], unavailableTelemetry: [] },
        evidenceButtonLabel: "Review Details",
        historicalComparison: "Historical comparison evidence supports a change from the normal pattern.",
        affectedVariables: ["temperature", "humidity"],
        emptyState: {
          title: "No current observations.",
          subtitle: "Telemetry is being monitored.",
          detail: "No structural changes detected.",
        },
      },
      currentSession: {
        hasReliableOperatorEvidence: true,
        reviewReadiness: "ready",
        latestUploadResult: {
          job_id: "job-current-1",
          observation_type: "trajectory_drift",
          drift_metrics: { baseline_distance: 0.7, drift_index: 0.7 },
          timestamp_profile: { first_timestamp: "2026-06-16T00:00:00Z", last_timestamp: "2026-06-16T04:00:00Z" },
          filename: "telemetry.csv",
        },
      },
    });

    await waitFor(() => expect(screen.getAllByText("Behavior Change Detected").length).toBeGreaterThan(0));
    expect(screen.getAllByText(/Historical comparison evidence/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Affected variables: temperature, humidity/i)).toBeTruthy();
  });


  it("keeps feedback locked until the evidence record is persisted", async () => {
    installLocalStorageMock();
    renderWorkspace({
      canonicalFinding: {
        exists: true,
        runId: "job-current-2",
        status: "Behavior Change Detected",
        confidence: "Moderate",
        summary: "System behavior has moved away from its historical operating pattern.",
        whyItMatters: "The observed relationships between system variables have changed.",
        reviewNext: "Review supporting evidence.",
        supportingEvidence: ["Affected variables: temperature, humidity."],
        technicalDetails: [{ label: "Behavior duration", value: "4h" }],
        dataQuality: { missingBaselineValues: [], missingRecentValues: [], unavailableTelemetry: [] },
        evidenceButtonLabel: "Review Details",
        historicalComparison: "Historical comparison evidence supports a change from the normal pattern.",
        affectedVariables: ["temperature", "humidity"],
        emptyState: {
          title: "No current observations.",
          subtitle: "Telemetry is being monitored.",
          detail: "No structural changes detected.",
        },
      },
      currentSession: {
        hasReliableOperatorEvidence: true,
        reviewReadiness: "ready",
        latestUploadResult: {
          job_id: "job-current-2",
          observation_type: "trajectory_drift",
          drift_metrics: { baseline_distance: 0.7, drift_index: 0.7 },
          timestamp_profile: { first_timestamp: "2026-06-16T00:00:00Z", last_timestamp: "2026-06-16T04:00:00Z" },
          filename: "telemetry.csv",
        },
      },
    });

    await waitFor(() => expect(screen.getAllByRole("button", { name: "Save Review" }).length).toBeGreaterThan(0));
    expect(screen.getAllByRole("button", { name: "Save Review" })[0].disabled).toBe(true);
    expect(screen.getByText(/feedback unlocks after the system record is persisted/i)).toBeTruthy();
  });


  it("renders validation history, intervention comparison, and submits action feedback", async () => {
    installLocalStorageMock();
    const run = {
      run_id: "validation-run-1",
      source_type: "csv_upload",
      source_name: "telemetry.csv",
      status: "completed",
      created_at: "2026-06-16T00:00:00Z",
      observation_type: "trajectory_drift",
      observation_status: "open",
      variables: ["temperature", "humidity"],
      drift_metrics: { baseline_distance: 0.7 },
      evidence_summary: ["System behavior changed."],
      validation_event_history: [{
        category: "maintenance_event",
        category_label: "maintenance event",
        status: "confirmed",
        outcome: "action_taken",
        action_taken: "Cleaned coil and reset airflow schedule",
        note: "Observed after maintenance",
        recorded_at: "2026-06-16T05:00:00Z",
      }],
      before_after_intervention: {
        available: true,
        summary: "Compared with the prior reviewed event, the follow-up signal improved.",
        direction: "improved",
        delta: -0.22,
      },
    };
    const apiFetch = vi.fn(async (url, options = {}) => {
      if (String(url).includes("/feedback")) {
        return createResponse({ ...run, run_id: "validation-run-1", latest_feedback_category: "false_positive" });
      }
      return createResponse({ runs: [run] });
    });

    renderWorkspace({
      apiFetch,
      canonicalFinding: {
        exists: true,
        runId: "validation-run-1",
        status: "Behavior Change Detected",
        confidence: "High",
        summary: "System behavior changed.",
        whyItMatters: "The observed relationships between system variables have changed.",
        reviewNext: "Review supporting evidence.",
        supportingEvidence: ["Affected variables: temperature, humidity."],
        technicalDetails: [],
        dataQuality: { missingBaselineValues: [], missingRecentValues: [], unavailableTelemetry: [] },
        evidenceButtonLabel: "Review Details",
        historicalComparison: "Historical comparison evidence supports a change from the normal pattern.",
        affectedVariables: ["temperature", "humidity"],
        emptyState: {
          title: "No current observations.",
          subtitle: "Telemetry is being monitored.",
          detail: "No structural changes detected.",
        },
      },
    });

    await waitFor(() => expect(screen.getByText("Labeled event history")).toBeTruthy());
    expect(screen.getByText(/Cleaned coil and reset airflow schedule/i)).toBeTruthy();
    expect(screen.getByText("Before/after intervention")).toBeTruthy();
    expect(screen.getByText(/follow-up signal improved/i)).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Feedback category"), { target: { value: "false_positive" } });
    fireEvent.change(screen.getByLabelText("Validation outcome"), { target: { value: "false_positive" } });
    fireEvent.change(screen.getByPlaceholderText("Action taken or follow-up"), { target: { value: "Marked as false positive after operator review" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Save Review" })[0]);

    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith(
      "/api/evidence/runs/validation-run-1/feedback",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          category: "false_positive",
          outcome: "false_positive",
          action_taken: "Marked as false positive after operator review",
          note: null,
        }),
      }),
    ));
  });

  it("loads issue history in bounded pages", async () => {
    installLocalStorageMock();
    const buildRun = (index) => ({
      run_id: `run-${index}`,
      source_type: "csv_upload",
      source_name: "telemetry.csv",
      status: "completed",
      created_at: new Date(Date.UTC(2026, 0, 1, 0, index)).toISOString(),
      observation_type: "trajectory_drift",
      observation_status: "open",
      variables: ["temperature", "humidity"],
      drift_metrics: { baseline_distance: index / 100 },
      evidence_summary: ["System behavior changed."],
      data_conditions: ["complete"],
    });
    const apiFetch = vi.fn(async (url) => {
      if (String(url).includes("offset=50")) {
        return createResponse({ runs: Array.from({ length: 10 }, (_, index) => buildRun(index + 50)), has_more: false, next_offset: null });
      }
      return createResponse({ runs: Array.from({ length: 50 }, (_, index) => buildRun(index)), has_more: true, next_offset: 50 });
    });

    renderWorkspace({ apiFetch });

    const loadOlder = await screen.findByRole("button", { name: "Load older issues" });
    expect(apiFetch).toHaveBeenCalledWith("/api/evidence/runs?limit=50&offset=0", { accessCode: "" });
    fireEvent.click(loadOlder);

    await waitFor(() => expect(screen.getByText("60 issue records loaded.")).toBeTruthy());
    expect(apiFetch).toHaveBeenCalledWith("/api/evidence/runs?limit=50&offset=50", { accessCode: "" });
    expect(screen.queryByRole("button", { name: "Load older issues" })).toBeNull();
  });

});
