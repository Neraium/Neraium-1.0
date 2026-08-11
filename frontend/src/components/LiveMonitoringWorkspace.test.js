/* @vitest-environment jsdom */
import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LiveMonitoringWorkspace, { LIVE_MONITORING_POLL_INTERVAL_MS } from "./LiveMonitoringWorkspace";
import { fetchLiveMonitoringSnapshot } from "../services/api/liveMonitoringApi";

vi.mock("../services/api/liveMonitoringApi", () => ({
  fetchLiveMonitoringSnapshot: vi.fn(),
}));

const CONFIGURATION = {
  system_id: "resort-chilled-water",
  enabled: true,
  approved_baseline_id: "bdm-live-1",
  next_analysis_at: "2026-08-01T12:15:00Z",
  current_status: "enabled",
};

const HEALTHY_SNAPSHOT = {
  status: "complete",
  refreshedAt: "2026-08-01T12:10:00Z",
  errors: {},
  configurations: [CONFIGURATION],
  ingestionHealth: [{
    system_id: "resort-chilled-water",
    source: "historian-rest",
    status: "healthy",
    last_telemetry_timestamp: "2026-08-01T12:09:00Z",
    last_successful_ingestion_at: "2026-08-01T12:09:10Z",
    accepted_count: 480,
    rejected_count: 2,
    latest_error_or_warning: null,
  }],
  analysisHealth: [{
    system_id: "resort-chilled-water",
    current_status: "healthy",
    last_successful_run_at: "2026-08-01T12:05:00Z",
    next_scheduled_run: "2026-08-01T12:15:00Z",
    current_window_coverage: 96.5,
    latest_skipped_reason: null,
    latest_error: null,
    consecutive_failures: 0,
  }],
  findings: [
    {
      finding_id: "finding-open",
      system_id: "resort-chilled-water",
      relationship_identity: "expected:all_operation:pump_power:flow",
      finding_classification: { type: "unexplained_systemic_change", label: "Unexplained systemic change", certainty_limit: "Root cause was not established." },
      current_state: "open",
      first_detected_at: "2026-08-01T11:02:00Z",
      last_observed_at: "2026-08-01T12:00:00Z",
      persistence_state: { persistent: true, support_fraction: 1 },
      severity_score: 72.5,
      latest_evidence: {
        run_id: "run-open",
        source_name: "live:resort-chilled-water",
        rows_accepted: 30,
        evidence_summary: ["pump_power and flow changed from their approved baseline."],
        timestamps: { upload_start: "2026-08-01T11:00:00Z", upload_end: "2026-08-01T12:00:00Z" },
        drift_metrics: { coupling_delta: -0.72 },
        evidence_hash: "evidence-hash-open",
      },
    },
    {
      finding_id: "finding-observing",
      system_id: "resort-chilled-water",
      relationship_identity: "expected:all_operation:power:pressure",
      finding_classification: { label: "Possible instrumentation issue" },
      current_state: "observing",
      first_detected_at: "2026-08-01T11:30:00Z",
      last_observed_at: "2026-08-01T12:00:00Z",
      persistence_state: { persistent: false, support_fraction: 0.5 },
      severity_score: null,
      latest_evidence: { evidence_summary: ["Power and pressure relationship changed."] },
    },
    {
      finding_id: "finding-resolved",
      system_id: "resort-chilled-water",
      relationship_identity: "expected:all_operation:temperature:load",
      finding_classification: { label: "Known operational change" },
      current_state: "resolved",
      first_detected_at: "2026-07-31T10:00:00Z",
      last_observed_at: "2026-07-31T12:00:00Z",
      persistence_state: { persistent: true },
      severity_score: 35,
      latest_evidence: { evidence_summary: ["Temperature and load returned to baseline alignment."] },
    },
  ],
  runs: [{
    run_id: "run-1",
    system_id: "resort-chilled-water",
    status: "completed",
    started_at: "2026-08-01T12:05:00Z",
    completed_at: "2026-08-01T12:05:05Z",
    window_start: "2026-08-01T11:00:00Z",
    window_end: "2026-08-01T12:00:00Z",
    coverage: 96.5,
    rows_analyzed: 30,
    signals_analyzed: 2,
    created_findings_count: 1,
    updated_findings_count: 0,
    resolved_findings_count: 0,
    skipped_reason: null,
    error_summary: null,
  }],
};

function emptySnapshot(overrides = {}) {
  return {
    status: "complete",
    refreshedAt: "2026-08-01T12:10:00Z",
    errors: {},
    configurations: [],
    ingestionHealth: [],
    analysisHealth: [],
    findings: [],
    runs: [],
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("Live Monitoring workspace", () => {
  it("shows the existing workspace loading experience while the first snapshot is pending", () => {
    fetchLiveMonitoringSnapshot.mockReturnValue(new Promise(() => {}));
    render(React.createElement(LiveMonitoringWorkspace, { apiFetch: vi.fn() }));

    expect(screen.getByLabelText("Opening Live Monitoring")).toBeTruthy();
    expect(screen.getByText("Loading telemetry, rolling analysis, and finding state.").className).toContain("sr-only");
  });

  it("renders configured systems, finding lifecycle state, health, scheduling, and runs", async () => {
    fetchLiveMonitoringSnapshot.mockResolvedValue(HEALTHY_SNAPSHOT);
    render(React.createElement(LiveMonitoringWorkspace, { apiFetch: vi.fn() }));

    expect(await screen.findByRole("heading", { name: "Live Monitoring", level: 1 })).toBeTruthy();
    const summary = screen.getByRole("region", { name: "Live Monitoring summary" });
    expect(within(summary).getByText("Systems monitored")).toBeTruthy();
    expect(within(summary).getByText("1 configured")).toBeTruthy();
    expect(screen.getAllByText("resort-chilled-water").length).toBeGreaterThan(0);
    expect(screen.getAllByText("96.5%").length).toBeGreaterThan(0);
    expect(screen.getByText("Unexplained systemic change")).toBeTruthy();
    expect(screen.getByText("Persistent: Yes · Support: 100%")).toBeTruthy();
    expect(screen.getByText("72.5")).toBeTruthy();
    expect(screen.getByText("Transport and analysis status only. These states are not equipment findings.")).toBeTruthy();
    expect(screen.getByText("1 created · 0 updated · 0 resolved")).toBeTruthy();
  });

  it("uses finding-sidecar lifecycle state instead of stale live-analysis state", async () => {
    fetchLiveMonitoringSnapshot.mockResolvedValue(HEALTHY_SNAPSHOT);
    const apiFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        findings: [{
          finding_id: "finding-open",
          source: { kind: "live_finding", id: "finding-open", finding_key: "finding-open" },
          evidence: {},
          workflow: {
            version: 2,
            status: "resolved",
            recommended_priority: "high",
            user_priority: null,
            effective_priority: "high",
            assignment: { target_type: "team", label: "Mechanical" },
            due_at: null,
            manager_note: null,
            work_order_reference: null,
            external_reference: null,
            validation_outcome: "issue_found",
            validation_note: null,
            latest_feedback: null,
            resolution: { outcome: "issue_found", note: "Seal leak confirmed." },
            updated_at: "2026-08-01T12:11:00Z",
            updated_by: "operator@example.com",
          },
          activity: { count: 2, latest_event_at: "2026-08-01T12:11:00Z", url: "/api/findings/finding-open/activity" },
        }],
        limit: 100,
        offset: 0,
        has_more: false,
        next_offset: null,
      }),
    });
    render(React.createElement(LiveMonitoringWorkspace, { apiFetch }));

    await screen.findByRole("heading", { name: "Live Monitoring", level: 1 });
    const activePanel = screen.getByRole("heading", { name: "Active findings", level: 2 }).closest("section");
    const resolvedPanel = screen.getByRole("heading", { name: "Recently resolved findings", level: 2 }).closest("section");
    await waitFor(() => expect(within(activePanel).getByText("No active findings")).toBeTruthy());
    expect(within(resolvedPanel).getByText("Unexplained systemic change")).toBeTruthy();
    expect(within(resolvedPanel).getAllByText("Resolved").length).toBeGreaterThanOrEqual(2);
    expect(within(resolvedPanel).getByText("Mechanical")).toBeTruthy();
  });

  it("opens backend-supplied supporting evidence in the shared evidence drawer", async () => {
    fetchLiveMonitoringSnapshot.mockResolvedValue(HEALTHY_SNAPSHOT);
    render(React.createElement(LiveMonitoringWorkspace, { apiFetch: vi.fn() }));
    await screen.findByRole("heading", { name: "Live Monitoring", level: 1 });

    fireEvent.click(screen.getAllByRole("button", { name: "View evidence" })[0]);

    const drawer = screen.getByRole("dialog", { name: "expected:all_operation:pump_power:flow" });
    expect(drawer).toBeTruthy();
    expect(within(drawer).getAllByText("pump_power and flow changed from their approved baseline.").length).toBeGreaterThan(0);
    expect(screen.getByText("evidence-hash-open")).toBeTruthy();
    expect(screen.getByText("Unavailable", { selector: ".evidence-drawer__confidence strong" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Close evidence drawer" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows honest empty states for no systems, telemetry, findings, or runs", async () => {
    fetchLiveMonitoringSnapshot.mockResolvedValue(emptySnapshot());
    render(React.createElement(LiveMonitoringWorkspace, { apiFetch: vi.fn() }));

    await screen.findByRole("heading", { name: "Live Monitoring", level: 1 });
    expect(screen.getAllByText("No systems configured").length).toBeGreaterThan(0);
    expect(screen.getByText("No active findings")).toBeTruthy();
    expect(screen.getByText("No observing findings")).toBeTruthy();
    expect(screen.getByText("No recently resolved findings")).toBeTruthy();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(screen.getByText("Never run")).toBeTruthy();
  });

  it("keeps delayed telemetry, missing baseline, and failed analysis separate from findings", async () => {
    fetchLiveMonitoringSnapshot.mockResolvedValue(emptySnapshot({
      configurations: [
        { ...CONFIGURATION, system_id: "waiting-system" },
        { ...CONFIGURATION, system_id: "delayed-system" },
        { ...CONFIGURATION, system_id: "baseline-system", approved_baseline_id: null },
        { ...CONFIGURATION, system_id: "failed-system" },
      ],
      ingestionHealth: [{
        system_id: "delayed-system", source: "historian", status: "delayed",
        last_telemetry_timestamp: "2026-08-01T10:00:00Z", last_successful_ingestion_at: "2026-08-01T10:00:05Z",
        accepted_count: 10, rejected_count: 0, latest_error_or_warning: "telemetry_delayed",
      }],
      analysisHealth: [
        { system_id: "baseline-system", current_status: "missing_baseline", current_window_coverage: 0, consecutive_failures: 0 },
        { system_id: "failed-system", current_status: "error", current_window_coverage: 82, consecutive_failures: 2, latest_error: "Live analysis failed (RuntimeError)." },
      ],
      runs: [{
        run_id: "failed-run", system_id: "failed-system", status: "failed", created_at: "2026-08-01T12:00:00Z",
        window_start: "2026-08-01T11:00:00Z", window_end: "2026-08-01T12:00:00Z", coverage: 82,
        rows_analyzed: 0, signals_analyzed: 0, created_findings_count: 0, updated_findings_count: 0, resolved_findings_count: 0,
        error_summary: "Live analysis failed (RuntimeError).",
      }],
    }));
    render(React.createElement(LiveMonitoringWorkspace, { apiFetch: vi.fn() }));

    await screen.findByRole("heading", { name: "Live Monitoring", level: 1 });
    expect(screen.getAllByText("Waiting for telemetry").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Delayed/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Missing Baseline").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Live Analysis Failed (RuntimeError).").length).toBeGreaterThan(0);
    expect(screen.getByText("No active findings")).toBeTruthy();
    expect(screen.queryByText(/equipment issue/i)).toBeNull();
  });

  it("renders partial, unauthorized, and network error states", async () => {
    fetchLiveMonitoringSnapshot.mockResolvedValueOnce(emptySnapshot({
      status: "partial",
      configurations: [CONFIGURATION],
      errors: { ingestionHealth: { kind: "network" }, analysisHealth: { kind: "http" } },
    }));
    const partial = render(React.createElement(LiveMonitoringWorkspace, { apiFetch: vi.fn() }));
    expect(await screen.findByText("Partial data")).toBeTruthy();
    expect(screen.getByText("Unavailable: Telemetry health, Analysis health.")).toBeTruthy();
    const systemCard = screen.getByRole("heading", { name: "resort-chilled-water", level: 3 }).closest("article");
    expect(within(systemCard).getAllByText("Unavailable").length).toBeGreaterThanOrEqual(3);
    partial.unmount();

    fetchLiveMonitoringSnapshot.mockResolvedValueOnce(emptySnapshot({ status: "unauthorized" }));
    const unauthorized = render(React.createElement(LiveMonitoringWorkspace, { apiFetch: vi.fn() }));
    expect(await screen.findByText("Live Monitoring access unavailable")).toBeTruthy();
    unauthorized.unmount();

    fetchLiveMonitoringSnapshot.mockResolvedValueOnce(emptySnapshot({ status: "error" }));
    render(React.createElement(LiveMonitoringWorkspace, { apiFetch: vi.fn() }));
    expect(await screen.findByText("Live Monitoring unavailable")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("supports manual refresh without starting a duplicate request", async () => {
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    fetchLiveMonitoringSnapshot.mockResolvedValueOnce(emptySnapshot()).mockReturnValueOnce(pending);
    render(React.createElement(LiveMonitoringWorkspace, { apiFetch: vi.fn() }));
    await screen.findByRole("heading", { name: "Live Monitoring", level: 1 });

    const refresh = screen.getByRole("button", { name: "Refresh" });
    fireEvent.click(refresh);
    fireEvent.click(screen.getByRole("button", { name: "Refreshing…" }));
    expect(fetchLiveMonitoringSnapshot).toHaveBeenCalledTimes(2);

    release({ ...HEALTHY_SNAPSHOT, refreshedAt: "2026-08-01T12:20:00Z" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh" })).toBeTruthy());
    expect(screen.getByText("1 configured")).toBeTruthy();
  });

  it("polls while visible, pauses while hidden, and refreshes after visibility returns", async () => {
    vi.useFakeTimers();
    let visibility = "visible";
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => visibility });
    fetchLiveMonitoringSnapshot.mockResolvedValue(emptySnapshot());

    render(React.createElement(LiveMonitoringWorkspace, { apiFetch: vi.fn() }));
    await act(async () => {});
    expect(fetchLiveMonitoringSnapshot).toHaveBeenCalledTimes(1);

    await act(async () => { vi.advanceTimersByTime(LIVE_MONITORING_POLL_INTERVAL_MS); });
    expect(fetchLiveMonitoringSnapshot).toHaveBeenCalledTimes(2);

    visibility = "hidden";
    fireEvent(document, new Event("visibilitychange"));
    await act(async () => { vi.advanceTimersByTime(LIVE_MONITORING_POLL_INTERVAL_MS * 2); });
    expect(fetchLiveMonitoringSnapshot).toHaveBeenCalledTimes(2);

    visibility = "visible";
    fireEvent(document, new Event("visibilitychange"));
    await act(async () => {});
    expect(fetchLiveMonitoringSnapshot).toHaveBeenCalledTimes(3);
  });
});
