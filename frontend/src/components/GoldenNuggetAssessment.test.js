/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import GoldenNuggetAssessment from "./GoldenNuggetAssessment";

const mapping = {
  baseline_timestamp_column: "timestamp",
  comparison_timestamp_column: "timestamp",
  signals: [
    { id: "demand", name: "Pump demand", baseline_column: "pump_kw", comparison_column: "pump_kw", unit: "kW", system_name: "Chilled-water distribution loop", role: "input", include: true },
    { id: "flow", name: "Loop flow", baseline_column: "flow_gpm", comparison_column: "flow_gpm", unit: "gpm", system_name: "Chilled-water distribution loop", role: "response", include: true },
  ],
};

const intake = {
  assessment_id: "pilot-test",
  status: "mapping_required",
  updated_at: "2026-07-31T00:00:00Z",
  datasets: { baseline: { filename: "baseline.csv" }, comparison: { filename: "comparison.csv" } },
  schemas: {
    baseline: {
      row_count: 400,
      column_count: 4,
      columns: [
        { name: "timestamp" }, { name: "pump_kw" }, { name: "flow_gpm" }, { name: "operator_note" },
      ],
      unusable_columns: [{ column: "operator_note", reasons: ["Only 0% of populated values are numeric."] }],
    },
    comparison: {
      row_count: 420,
      column_count: 4,
      columns: [
        { name: "timestamp" }, { name: "pump_kw" }, { name: "flow_gpm" }, { name: "operator_note" },
      ],
      unusable_columns: [{ column: "operator_note", reasons: ["Only 0% of populated values are numeric."] }],
    },
  },
  mapping,
  mapping_validation: { ready: true, errors: [], warnings: [] },
  quality_gate: null,
  operating_modes: [],
  analysis: null,
  event_backtest: null,
  feedback_history: [],
};

const relationship = {
  relationship_id: "rel-one",
  relationship: "Pump demand ↔ Loop flow",
  operating_mode: "stable high load",
  what_changed: "The mode-matched relationship moved outside its baseline behavior.",
  before_behavior: { correlation: 0.91, slope: 2.1, records: 120 },
  after_behavior: { correlation: 0.22, slope: 0.4, records: 110 },
  magnitude: { absolute_correlation_change: 0.69, slope_change_percent: 81 },
  persistence: {
    supporting_windows: 3,
    assessed_windows: 4,
    windows: [
      { start: "2026-07-20T01:00:00Z", deviation_score: 5.98, supports_change: true },
      { start: "2026-07-25T02:00:00Z", deviation_score: 0.60, supports_change: false },
    ],
  },
  start_time: "2026-07-20T01:00:00Z",
  data_quality_limitations: [],
  exact_records: { record_count: 230, sha256: "a".repeat(64), download_url: "/api/pilot-assessments/pilot-test/records/rel-one.csv" },
};

const analyzed = {
  ...intake,
  status: "analysis_complete",
  updated_at: "2026-07-31T01:00:00Z",
  analysis_completed_at: "2026-07-31T01:00:00Z",
  quality_gate: {
    passed: true,
    summary: "Baseline accepted with 8 usable signals.",
    included_signal_count: 8,
    excluded_signal_count: 0,
    blocking_reasons: [],
    warnings: [
      "7 duplicate baseline timestamps were excluded.",
      "Comparison-period quality is limited for: Tower enable status.",
    ],
    baseline_period: { time_coverage: 0.98, usable_timestamp_rows: 400 },
    comparison_period: { usable_timestamp_rows: 420 },
    signals: mapping.signals.map((signal) => ({ ...signal, included: true, exclusion_reasons: [], baseline: { coverage: 0.98, flags: [] } })),
  },
  operating_modes: [
    { mode: "startup", baseline_records: 8, comparison_records: 9, comparable: false, used_for_findings: false },
    { mode: "stable high load", baseline_records: 120, comparison_records: 110, comparable: true, used_for_findings: true },
  ],
  analysis: {
    conclusion: "Neraium surfaced one evidence-backed system finding before any event timestamp was supplied.",
    findings: [{
      finding_id: "finding-1",
      title: "Pump demand no longer matches hydraulic response",
      system_name: "Chilled-water distribution loop",
      summary: "1 supporting mode-matched relationship change was persistent.",
      evidence_count: 1,
      first_surfaced_at: "2026-07-20T01:00:00Z",
      last_observed_at: "2026-07-25T01:00:00Z",
      persisted: true,
      relationships: [relationship],
    }],
  },
  feedback_history: [],
};

function jsonResponse(payload, ok = true) {
  return { ok, json: async () => payload };
}

afterEach(() => cleanup());

describe("GoldenNuggetAssessment", () => {
  it("runs intake, blinded analysis, event reveal, append-only feedback, and report export in order", async () => {
    let current = null;
    const apiFetch = vi.fn(async (path, options = {}) => {
      if (path === "/api/pilot-assessments?limit=1") return jsonResponse({ assessments: [] });
      if (path === "/api/pilot-assessments/intake") {
        current = intake;
        return jsonResponse(current);
      }
      if (path.endsWith("/mapping")) {
        current = { ...intake, status: "ready_to_analyze" };
        return jsonResponse(current);
      }
      if (path.endsWith("/analyze")) {
        current = analyzed;
        return jsonResponse(current);
      }
      if (path.endsWith("/event")) {
        current = {
          ...analyzed,
          event_backtest: {
            event_label: "Tower outage",
            event_timestamp: "2026-07-24T00:00:00Z",
            repair_timestamp: "2026-07-25T00:00:00Z",
            analysis_was_blinded: true,
            findings: [{
              finding_id: "finding-1",
              first_surfaced_at: "2026-07-20T01:00:00Z",
              lead_time_hours: 139.92,
              surfaced_before_event: true,
              persisted_through_event: true,
              disappeared_after_repair: true,
            }],
          },
        };
        return jsonResponse(current);
      }
      if (path.endsWith("/feedback")) {
        current = {
          ...current,
          feedback_history: [{ feedback_id: "feedback-1", category: "needs_investigation", note: "Review the pump staging record.", recorded_at: "2026-07-31T02:00:00Z", recorded_by: "engineer@test" }],
        };
        return jsonResponse(current);
      }
      return jsonResponse({}, false);
    });
    render(React.createElement(GoldenNuggetAssessment, { apiFetch, accessCode: "" }));

    expect(screen.queryByLabelText("Known event timestamp (UTC)")).toBeNull();
    const csv = new File(["timestamp,pump_kw,flow_gpm\n2026-01-01T00:00:00Z,1,2"], "tower.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/Baseline period CSV/), { target: { files: [csv] } });
    fireEvent.change(screen.getByLabelText(/Later comparison period CSV/), { target: { files: [csv] } });
    fireEvent.submit(screen.getByRole("button", { name: "Inspect datasets" }).closest("form"));

    expect(await screen.findByRole("heading", { name: "Column inspection complete" })).toBeTruthy();
    expect(screen.getAllByText(/missing or unusable columns must be reviewed/i)).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Run blinded analysis" })).toBeTruthy();
    expect(screen.queryByText("Tower outage")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Run blinded analysis" }));
    expect(await screen.findByRole("heading", { name: "Pump demand no longer matches expected flow response" })).toBeTruthy();
    expect(screen.getByText("The system required a different level of pump demand to produce the hydraulic response learned during the baseline period.")).toBeTruthy();
    expect(screen.getByText("1 supporting relationship change")).toBeTruthy();
    const dataQualityHeading = screen.getByRole("heading", { name: "Data quality notes" });
    expect(dataQualityHeading.closest(".golden-finding")).toBeNull();
    expect(screen.getByText("7 duplicate baseline timestamps were excluded")).toBeTruthy();
    expect(screen.getByText("Tower-enable coverage was limited during the comparison period")).toBeTruthy();
    expect(screen.queryByText("Exact records (230)")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "View relationship evidence" }));
    expect(screen.getByText("Exact records (230)")).toBeTruthy();
    expect(screen.getByLabelText("Known event timestamp (UTC)")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Known event or work-order label"), { target: { value: "Tower outage" } });
    fireEvent.change(screen.getByLabelText("Known event timestamp (UTC)"), { target: { value: "2026-07-24T00:00" } });
    fireEvent.change(screen.getByLabelText("Repair or recovery timestamp (UTC, optional)"), { target: { value: "2026-07-25T00:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Run event backtest" }));
    expect(await screen.findByText("Blinded analysis confirmed")).toBeTruthy();
    expect(screen.getByText("139.92 hours before event")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Why this finding is credible" })).toBeTruthy();
    expect(screen.getByText("Detected 139.92 hours before the recorded event")).toBeTruthy();
    expect(screen.getByText("Persisted through the event")).toBeTruthy();
    expect(screen.getByText("Supported by 1 changed relationship")).toBeTruthy();
    expect(screen.getByText("Disappeared after repair")).toBeTruthy();
    expect(screen.getByText("Median behavioral deviation decreased from 5.98 before repair to 0.60 after repair.")).toBeTruthy();
    expect(screen.getByText("89.97% reduction")).toBeTruthy();

    fireEvent.click(screen.getByText("Needs investigation"));
    fireEvent.change(screen.getByLabelText("Engineer notes"), { target: { value: "Review the pump staging record." } });
    fireEvent.click(screen.getByRole("button", { name: "Append feedback" }));
    expect(await screen.findByText("Review the pump staging record.")).toBeTruthy();

    const report = screen.getByRole("link", { name: "Export HTML report" });
    expect(report.getAttribute("href")).toBe("http://127.0.0.1:8010/api/pilot-assessments/pilot-test/report.html");
    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith(
      "/api/pilot-assessments/pilot-test/event",
      expect.objectContaining({ method: "POST" }),
    ));
  });
});
