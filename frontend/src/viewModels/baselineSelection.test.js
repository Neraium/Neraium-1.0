/* @vitest-environment jsdom */
import { afterEach, describe, expect, it } from "vitest";
import {
  analysisBelongsToBaseline,
  baselineAnalysisRoutePath,
  baselineIdentityFromResult,
  baselineRoutePath,
  parseBaselineAnalysisRoute,
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
    expect(baselineRoutePath("portfolio-a", "baseline-b")).toBe("/portfolio/portfolio-a/baselines/baseline-b");
    expect(parseBaselineRoute("/portfolio/portfolio-a/baselines/baseline-b")).toEqual({ portfolioId: "portfolio-a", systemId: "portfolio-a", baselineId: "baseline-b" });
    expect(parseBaselineRoute("/portfolio/portfolio-a/baselines")).toBeNull();
    expect(baselineAnalysisRoutePath("portfolio-a", "baseline-b", "run-c")).toBe("/portfolio/portfolio-a/baselines/baseline-b/analyses/run-c");
    expect(parseBaselineAnalysisRoute("/portfolio/portfolio-a/baselines/baseline-b/analyses/run-c")).toEqual({
      portfolioId: "portfolio-a",
      systemId: "portfolio-a",
      baselineId: "baseline-b",
      analysisRunId: "run-c",
    });
  });

  it("accepts only completed comparison identities owned by the exact baseline and system", () => {
    const identity = { portfolioId: "portfolio-a", systemId: "system-a", baselineId: "baseline-a" };
    const linked = {
      workflow: "analyze_new_data",
      portfolio_id: "portfolio-a",
      system_id: "system-a",
      baseline_id: "baseline-a",
      comparison_dataset_id: "run-a",
      analysis_run_id: "run-a",
      dataset_id: "run-a",
      job_id: "run-a",
      active_baseline_reference: { model_id: "baseline-a" },
    };

    expect(analysisBelongsToBaseline(linked, identity)).toBe(true);
    expect(analysisBelongsToBaseline({ ...linked, baseline_id: "baseline-b", active_baseline_reference: { model_id: "baseline-b" } }, identity)).toBe(false);
    expect(analysisBelongsToBaseline({ ...linked, portfolio_id: "portfolio-b" }, identity)).toBe(false);
    expect(analysisBelongsToBaseline({ ...linked, system_id: "system-b" }, identity)).toBe(false);
    expect(analysisBelongsToBaseline({ ...linked, comparison_dataset_id: "stale-dataset" }, identity)).toBe(false);
    expect(analysisBelongsToBaseline({ ...linked, workflow: "legacy_analysis" }, identity)).toBe(false);
  });
});
