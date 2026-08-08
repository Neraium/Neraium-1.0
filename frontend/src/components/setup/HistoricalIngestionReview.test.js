/* @vitest-environment jsdom */
import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import HistoricalIngestionReview from "./HistoricalIngestionReview";


const h = React.createElement;
const response = (payload, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  headers: { get: () => "application/json" },
  json: vi.fn().mockResolvedValue(payload),
});

function profile(overrides = {}) {
  return {
    dataset_id: "dataset-1",
    dataset_identity: "abcdef0123456789abcdef0123456789",
    revision: 1,
    summary: {
      signal_counts: {
        detected: 186,
        confidently_mapped: 143,
        need_review: 2,
        excluded: 22,
        unit_conflicts: 1,
        duplicate_candidates: 2,
        timestamp_gaps: 4,
        configuration_boundaries: 1,
      },
    },
    readiness: {
      outcome: "ready_with_limitations",
      limitations: ["The unresolved flow signal is excluded from unit-dependent methods."],
    },
    signal_profiles: [
      {
        canonical_signal_id: "sig-flow",
        source_column: "Mystery Flow",
        proposed_canonical_role: "flow",
      },
      {
        canonical_signal_id: "sig-temp",
        source_column: "SA-T",
        proposed_canonical_role: "supply_temperature",
      },
    ],
    review: {
      items: [
        { type: "unit", signal_id: "sig-flow", source_column: "Mystery Flow", reason: "Unit evidence needs review." },
        { type: "semantic_mapping", signal_id: "sig-temp", source_column: "SA-T", reason: "Semantic mapping needs review." },
        { type: "timestamp", signal_id: null, source_column: "Timestamp", reason: "Four major gaps were preserved." },
      ],
    },
    trust_dimensions: [
      { dimension: "timestamp_integrity", status: "medium", reasons: ["Four major gaps were preserved."] },
      { dimension: "unit_confidence", status: "review_required", reasons: ["One unit is unresolved."] },
    ],
    ...overrides,
  };
}

function jobProgress({ status = "processing", completed = 5, total = 10 } = {}) {
  const complete = status === "completed";
  const now = "2026-08-08T12:00:00+00:00";
  const operations = [
    ["receiving", "upload", "Receiving file", "completed"],
    ["source_persisted", "upload", "Source persisted", "completed"],
    ["parse_source", "validate", "Parse source", complete ? "completed" : status],
    ["readiness_evaluation", "validate", "Readiness evaluation", complete ? "completed" : "pending"],
  ].map(([id, stage, operationLabel, operationStatus]) => ({
    id,
    stage,
    label: operationLabel,
    status: operationStatus,
    completed_units: id === "parse_source" ? completed : operationStatus === "completed" ? 1 : null,
    total_units: id === "parse_source" ? total : operationStatus === "completed" ? 1 : null,
    percent_complete: operationStatus === "completed" ? 100 : id === "parse_source" ? Math.floor(completed * 100 / total) : null,
    unit_type: id === "parse_source" ? "rows" : "operation",
    message: id === "parse_source" ? `Parsed ${completed} of ${total} rows.` : null,
    started_at: now,
    updated_at: now,
    completed_at: operationStatus === "completed" ? now : null,
    metadata: {},
  }));
  return {
    contract_version: "job-progress.v1",
    job_id: "dataset-1",
    workflow: "historical_review",
    status,
    stage: complete ? "validate" : "validate",
    substage: complete ? "readiness_evaluation" : "parse_source",
    completed_units: complete ? 1 : completed,
    total_units: complete ? 1 : total,
    percent_complete: complete ? 100 : Math.floor(completed * 100 / total),
    unit_type: complete ? "operation" : "rows",
    message: complete ? "Canonical dataset review complete." : `Parsed ${completed} of ${total} rows.`,
    started_at: now,
    updated_at: now,
    elapsed_seconds: 4,
    last_worker_heartbeat_at: now,
    seconds_since_worker_heartbeat: 0,
    seconds_since_update: 0,
    stalled: false,
    retryable: null,
    error: null,
    metadata: {},
    workflow_steps: [
      { id: "upload", label: "Upload", status: "completed", completed_work_units: 2, total_work_units: 2, percent_complete: 100 },
      { id: "validate", label: "Validate", status: complete ? "completed" : "processing", completed_work_units: complete ? 2 : 0, total_work_units: 2, percent_complete: complete ? 100 : 25 },
    ],
    operations,
    overall_percent_complete: complete ? 100 : 62,
    overall_basis: "equal_completed_declared_substages",
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("HistoricalIngestionReview", () => {
  it("renders loading, focused review counts, limitations, and inspectable evidence", async () => {
    let resolveRequest;
    const apiFetch = vi.fn(() => new Promise((resolve) => { resolveRequest = resolve; }));
    render(h(HistoricalIngestionReview, { datasetId: "dataset-1", apiFetch, accessCode: "access" }));

    expect(screen.getByRole("status").textContent).toContain("Loading ingestion profile");
    resolveRequest(response(profile()));

    expect(await screen.findByRole("heading", { name: "Ready with documented limitations" })).toBeTruthy();
    expect(screen.getByLabelText("Ingestion trust summary").textContent).toContain("186");
    expect(screen.getByLabelText("Ingestion trust summary").textContent).toContain("143");
    expect(screen.getByText(/unresolved flow signal/i)).toBeTruthy();
    fireEvent.click(screen.getByText(/Inspect timestamp, quality/i));
    expect(screen.getAllByText(/Four major gaps were preserved/i)).toHaveLength(2);
  });

  it("submits only explicit mapping and unit decisions and announces the new revision", async () => {
    const updated = profile({ revision: 2, dataset_identity: "fedcba9876543210fedcba9876543210" });
    const apiFetch = vi.fn()
      .mockResolvedValueOnce(response(profile()))
      .mockResolvedValueOnce(response(updated));
    const onUpdated = vi.fn();
    render(h(HistoricalIngestionReview, { datasetId: "dataset-1", apiFetch, onUpdated }));

    fireEvent.change(await screen.findByLabelText("Confirmed source unit for Mystery Flow"), { target: { value: "gpm" } });
    fireEvent.change(screen.getByLabelText("Mapping decision for SA-T"), { target: { value: "choose_role" } });
    fireEvent.change(screen.getByLabelText("Canonical role for SA-T"), { target: { value: "supply_temperature" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Review Decisions" }));

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(2));
    const [path, options] = apiFetch.mock.calls[1];
    expect(path).toBe("/api/data/ingestion/v1/datasets/dataset-1/review");
    expect(options.method).toBe("PATCH");
    expect(JSON.parse(options.body)).toEqual({ decisions: [
      { signal_id: "sig-flow", unit: "gpm" },
      { signal_id: "sig-temp", mapping_action: "choose_role", canonical_role: "supply_temperature" },
    ] });
    expect((await screen.findByRole("status")).textContent).toContain("canonical dataset revision is ready for reanalysis");
    expect(onUpdated).toHaveBeenCalledWith(expect.objectContaining({ revision: 2, dataset_identity: updated.dataset_identity }));
  });

  it("polls and renders persisted backend progress while a review rebuild is running", async () => {
    let resolveReview;
    const reviewResponse = new Promise((resolve) => { resolveReview = resolve; });
    const apiFetch = vi.fn((path, options = {}) => {
      if (path.endsWith("/review") && options.method === "PATCH") return reviewResponse;
      if (path.includes("/upload-status/")) {
        return Promise.resolve(response({
          job_id: "dataset-1",
          status: "PROCESSING",
          processing_state: "historical_review",
          execution_state: "processing",
          job_progress: jobProgress(),
        }));
      }
      return Promise.resolve(response(profile()));
    });
    render(h(HistoricalIngestionReview, { datasetId: "dataset-1", apiFetch }));

    fireEvent.change(await screen.findByLabelText("Confirmed source unit for Mystery Flow"), { target: { value: "gpm" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Review Decisions" }));

    expect(await screen.findByLabelText("Backend job progress")).toBeTruthy();
    expect(screen.getByRole("progressbar", { name: "Parse source" }).getAttribute("aria-valuenow")).toBe("50");
    expect(screen.getByText("5 / 10 rows")).toBeTruthy();

    await act(async () => {
      resolveReview(response(profile({ revision: 2, job_progress: jobProgress({ status: "completed", completed: 10, total: 10 }) })));
      await reviewResponse;
    });
    expect(await screen.findByText("Canonical dataset review complete.")).toBeTruthy();
    expect(screen.getByText("Completed")).toBeTruthy();
  });

  it("shows a useful error state when the profile cannot be loaded", async () => {
    const apiFetch = vi.fn().mockResolvedValue(response({ detail: "Profile is unavailable for this workspace." }, 404));
    render(h(HistoricalIngestionReview, { datasetId: "missing", apiFetch }));

    expect((await screen.findByRole("alert")).textContent).toContain("Profile is unavailable for this workspace");
  });

  it("does not require review when all high-confidence signals are ready", () => {
    render(h(HistoricalIngestionReview, {
      datasetId: "ready",
      initialProfile: profile({
        readiness: { outcome: "ready", limitations: [] },
        review: { items: [] },
      }),
    }));

    expect(screen.getByRole("heading", { name: "Ready for analysis" })).toBeTruthy();
    expect(screen.getByText(/No mapping or unit decisions are required/i)).toBeTruthy();
  });
});
