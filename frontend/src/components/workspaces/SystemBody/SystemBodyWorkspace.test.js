/* @vitest-environment jsdom */
import React from "react";
import fs from "node:fs";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SystemBodyWorkspace from "./SystemBodyWorkspace";

const h = React.createElement;

vi.mock("./SystemOrbPanel", () => ({
  default: () => h("div", { "data-testid": "system-orb-panel" }),
}));

vi.mock("../../layout/PageContainer", () => ({
  default: ({ children, className }) => h("div", { className }, children),
}));

function readResultDetail(label, sectionName = "Evidence") {
  fireEvent.click(screen.getByRole("button", { name: sectionName }));
  const section = screen.getByLabelText(sectionName);
  const labelNode = within(section).getByText(label);
  return labelNode.nextElementSibling?.textContent;
}

function renderWorkspace(overrides = {}) {
  return render(
    h(SystemBodyWorkspace, Object.assign({
      systemState: "idle",
      uiState: "ready",
      coherence: 1,
      stateLabel: "No data yet",
      subtitle: "Upload data to begin.",
      connectionStatus: "idle",
      connectionTone: "pending",
      primaryMessage: "Upload data to begin.",
      lastUpdate: null,
      focusLabel: "No data yet",
      latestUploadSnapshot: { status: "empty" },
      latestUploadResult: null,
      liveSnapshot: null,
      latestReplayFrame: null,
    }, overrides)),
  );
}

afterEach(() => {
  cleanup();
});

describe("SystemBodyWorkspace empty state", () => {
  it("keeps the Gate settings control reachable by its stable accessible name", () => {
    renderWorkspace();

    expect(screen.getByRole("button", { name: "Open Gate settings" })).toBeTruthy();
  });

  it("surfaces detected telemetry domain in the Gate settings menu", () => {
    renderWorkspace({ domainDetection: { mode: "aquatic", source: "upload_shape", confidence: 0.88 } });

    fireEvent.click(screen.getByRole("button", { name: "Open Gate settings" }));

    expect(screen.getByText("Detected data type: Aquatic")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Data connections" })).toBeTruthy();
  });

  it("shows the no-upload state when no current session upload exists", () => {
    renderWorkspace();

    expect(screen.getAllByText("Awaiting Telemetry").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Analyze a system to begin" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Analyze System" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Issues" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Data Quality" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Evidence" })).toBeNull();
    expect(screen.queryByRole("button", { name: "View Issues" })).toBeNull();
    expect(screen.queryByText("Rows loaded")).toBeNull();
  });

  it("renders persisted latest upload only as previous upload until resumed", () => {
    const onResumePreviousUpload = vi.fn();
    renderWorkspace({
      persistedLatestUpload: {
        jobId: "stale-job",
        filename: "old-upload.csv",
        processedAt: "2026-06-01T12:00:00Z",
        result: {
          job_id: "stale-job",
          row_count: 51841,
          data_quality: { analysis_gate_state: "DEGRADED_READY", warnings: ["stale warning"] },
          sii_intelligence: { facility_state: "Monitoring" },
        },
        snapshot: { rows_processed: 51841 },
      },
      previousUploadHistory: [{ job_id: "stale-job", filename: "old-upload.csv", rows_processed: 51841 }],
      onResumePreviousUpload,
    });

    expect(screen.getByRole("heading", { name: "Analyze a system to begin" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Analyze System" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Resume Previous Analysis" })).toBeTruthy();
    expect(screen.getByLabelText("Previous upload").textContent).toContain("old-upload.csv");
    expect(screen.queryByText("Ready with warnings")).toBeNull();
    expect(screen.queryByText("51841")).toBeNull();
    expect(screen.queryByRole("button", { name: "View Issues" })).toBeNull();
  });

  it("enables review metrics after a completed analysis exists", () => {
    renderWorkspace({
      latestUploadSnapshot: { status: "complete", sii_completed: true, current_upload: { job_id: "job-42" } },
      latestUploadResult: {
        job_id: "job-42",
        observation_type: "trajectory_drift",
        drift_status: "elevated",
        timestamp_profile: { first_timestamp: "2026-06-15T00:00:00Z" },
        sii_completed: true,
        sii_intelligence: {
          facility_state: "drift",
          baseline_regime: "State Group B",
          instability_index: 0.72,
        },
      },
    });

    expect(screen.getByRole("button", { name: "View Issues" })).toBeTruthy();
    expect(readResultDetail("Historical comparison")).toBe("State Group B");
    expect(screen.queryByText("Operating pattern duration")).toBeNull();
  });

  it("does not render pending copy for a READY upload result", () => {
    renderWorkspace({
      latestUploadSnapshot: { status: "complete", sii_completed: true, current_upload: { job_id: "ready-job" } },
      latestUploadResult: {
        job_id: "ready-job",
        status: "complete",
        sii_completed: true,
        data_quality: { analysis_gate_state: "READY", readiness: "ready", warnings: [] },
        timestamp_profile: { first_timestamp: "2026-06-01T00:00:00Z", last_timestamp: "2026-06-03T00:00:00Z" },
        sii_intelligence: { facility_state: "Monitoring", baseline_regime: "Chilled-water stable", confidence: 0.9 },
      },
    });

    expect(screen.getAllByText("Analysis ready").length).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { name: "Analysis running" })).toBeNull();
    expect(screen.queryByText(/backend processing has not finished/i)).toBeNull();
    expect(readResultDetail("Operating pattern duration")).toBe("2d");
    expect(screen.queryByRole("button", { name: "Review Issues" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Review Evidence" })).toBeNull();
  });

  it("does not render pending copy for a DEGRADED_READY upload result", () => {
    renderWorkspace({
      latestUploadSnapshot: { status: "complete", sii_completed: true, current_upload: { job_id: "degraded-job" } },
      latestUploadResult: {
        job_id: "degraded-job",
        status: "complete",
        sii_completed: true,
        data_quality: { analysis_gate_state: "DEGRADED_READY", readiness: "ready", warnings: ["Sparse missing values detected; short numeric gaps interpolated."] },
        timestamp_profile: { first_timestamp: "2026-06-01T00:00:00Z", last_timestamp: "2026-06-01T06:00:00Z" },
        sii_intelligence: { facility_state: "Monitoring", baseline_regime: "Chilled-water warning", confidence: 0.68 },
      },
    });

    expect(screen.getAllByText("Ready with warnings").length).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { name: "Analysis running" })).toBeNull();
    expect(screen.queryByText(/backend processing has not finished/i)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Data Quality" }));
    expect(screen.getAllByText((text) => text.includes("Sparse missing values detected; short numeric gaps interpolated.")).length).toBeGreaterThan(0);
  });

  it("renders one pending card when backend analysis is actually pending", () => {
    renderWorkspace({
      latestUploadSnapshot: { status: "running_sii", current_upload: { job_id: "pending-job" } },
      latestUploadResult: {
        job_id: "pending-job",
        status: "running_sii",
        processing_state: "running_sii",
        data_quality: { analysis_gate_state: "PENDING", readiness: "pending" },
      },
    });

    expect(screen.getByRole("heading", { name: "Telemetry is still processing." })).toBeTruthy();
    expect(screen.getAllByText("Telemetry is present, but analysis is still running.")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Review Issues" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Review Evidence" })).toBeNull();
  });

  it("replaces impossible persistence with a history fallback when only an old start timestamp exists", () => {
    renderWorkspace({
      latestUploadSnapshot: { status: "complete", sii_completed: true, current_upload: { job_id: "old-job" } },
      latestUploadResult: {
        job_id: "old-job",
        status: "complete",
        sii_completed: true,
        data_quality: { analysis_gate_state: "READY", readiness: "ready" },
        timestamp_profile: { first_timestamp: "1970-01-01T00:00:00Z" },
        sii_intelligence: { facility_state: "Monitoring", baseline_regime: "Historical upload", confidence: 0.7 },
      },
    });

    fireEvent.click(screen.getByRole("button", { name: "Evidence" }));
    expect(screen.queryByText("Operating pattern duration")).toBeNull();
    expect(screen.queryByText(/20625d/)).toBeNull();
  });

  it("keeps mobile bottom spacing safe-area aware", () => {
    const css = fs.readFileSync(process.cwd() + "/src/styles/system-body/system-body-shell.css", "utf8")
      + fs.readFileSync(process.cwd() + "/src/styles/system-body/system-body-layout-fix.css", "utf8");

    expect(css).toContain("env(safe-area-inset-bottom, 0px)");
    expect(css).toContain("calc(72px + env(safe-area-inset-bottom, 0px))");
  });

});
