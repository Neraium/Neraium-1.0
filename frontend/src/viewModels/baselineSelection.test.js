/* @vitest-environment jsdom */
import { afterEach, describe, expect, it } from "vitest";
import {
  baselineIdentityFromResult,
  baselineRoutePath,
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
  });
});
