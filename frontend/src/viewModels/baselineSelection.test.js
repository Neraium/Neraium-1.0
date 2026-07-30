/* @vitest-environment jsdom */
import { afterEach, describe, expect, it } from "vitest";
import {
  analysisBelongsToBaseline,
  baselineAnalysisRoutePath,
  baselineComparisonRoutePath,
  baselineIdentityFromResult,
  baselineRoutePath,
  parseBaselineAnalysisRoute,
  parseBaselineComparisonRoute,
  parseBaselineRoute,
  persistBaselineSelection,
  readPersistedBaselineSelection,
} from "./baselineSelection";

afterEach(() => window.localStorage.clear());

describe("baseline selection identity", () => {
  it("captures and restores every completion identifier without array-order inference", () => {
    const identity = baselineIdentityFromResult({
      job_id: "job-a",
      upload_id: "upload-a",
      dataset_id: "dataset-a",
      baseline_candidate_id: "candidate-a",
      established_baseline_id: "baseline-a",
      portfolio_id: "portfolio-a",
      system_id: "system-a",
      candidate_model: { model_id: "candidate-a", source: {} },
    });

    expect(identity).toEqual({
      jobId: "job-a",
      uploadId: "upload-a",
      datasetId: "dataset-a",
      candidateId: "candidate-a",
      baselineId: "baseline-a",
      portfolioId: "portfolio-a",
      systemId: "system-a",
      stateSource: "completion_response",
    });
    persistBaselineSelection(identity);
    expect(readPersistedBaselineSelection("portfolio-a", "baseline-a")).toEqual({ ...identity, stateSource: "cache" });
  });

  it("round-trips explicit baseline routes and rejects ambiguous paths", () => {
    window.localStorage.setItem("neraium.current_workspace_id", "portfolio-a");
    expect(baselineRoutePath("portfolio-a", "baseline-b")).toBe("/baselines/baseline-b/ready");
    expect(parseBaselineRoute("/baselines/baseline-b/ready")).toMatchObject({ portfolioId: "portfolio-a", systemId: "portfolio-a", baselineId: "baseline-b" });
    expect(baselineComparisonRoutePath("portfolio-a", "baseline-b")).toBe("/baselines/baseline-b/comparisons/new");
    expect(parseBaselineComparisonRoute("/baselines/baseline-b/comparisons/new")).toMatchObject({ portfolioId: "portfolio-a", baselineId: "baseline-b" });
    expect(parseBaselineRoute("/baselines/baseline-b")).toBeNull();
    expect(baselineAnalysisRoutePath("portfolio-a", "baseline-b", "run-c")).toBe("/analyses/run-c");
    expect(parseBaselineAnalysisRoute("/analyses/run-c")).toEqual({ analysisRunId: "run-c" });
  });

  it("accepts only completed comparison identities owned by the exact baseline and system", () => {
    const identity = { portfolioId: "portfolio-a", systemId: "system-a", baselineId: "baseline-a" };
    const linked = {
      workflow: "analyze_new_data",
      status: "COMPLETE",
      processing_state: "complete",
      sii_completed: true,
      portfolio_id: "portfolio-a",
      system_id: "system-a",
      baseline_id: "baseline-a",
      baseline_dataset_id: "dataset-baseline-a",
      comparison_dataset_id: "dataset-comparison-a",
      comparison_analysis_id: "run-a",
      analysis_run_id: "run-a",
      dataset_id: "dataset-comparison-a",
      job_id: "run-a",
      active_baseline_reference: { model_id: "baseline-a", dataset_id: "dataset-baseline-a" },
    };

    expect(analysisBelongsToBaseline(linked, identity)).toBe(true);
    expect(analysisBelongsToBaseline({ ...linked, baseline_id: "baseline-b", active_baseline_reference: { model_id: "baseline-b" } }, identity)).toBe(false);
    expect(analysisBelongsToBaseline({ ...linked, portfolio_id: "portfolio-b" }, identity)).toBe(false);
    expect(analysisBelongsToBaseline({ ...linked, system_id: "system-b" }, identity)).toBe(false);
    expect(analysisBelongsToBaseline({ ...linked, comparison_dataset_id: "stale-dataset" }, identity)).toBe(false);
    expect(analysisBelongsToBaseline({ ...linked, workflow: "legacy_analysis" }, identity)).toBe(false);
    expect(analysisBelongsToBaseline({ ...linked, status: "PROCESSING" }, identity)).toBe(false);
    expect(analysisBelongsToBaseline({ ...linked, sii_completed: false }, identity)).toBe(false);
    expect(analysisBelongsToBaseline({ ...linked, baseline_dataset_id: "other-baseline-dataset" }, identity)).toBe(false);
  });
});
