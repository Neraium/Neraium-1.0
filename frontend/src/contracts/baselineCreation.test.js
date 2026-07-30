import { describe, expect, it } from "vitest";
import { BaselineCreationContractError, normalizeBaselineCreationResponse } from "./baselineCreation";

describe("baseline creation response contract", () => {
  it("normalizes a nested snake_case response into canonical camelCase fields", () => {
    const parsed = normalizeBaselineCreationResponse({
      data: {
        result: {
          status: "COMPLETE",
          job_id: "job-1",
          dataset_id: "dataset-1",
          established_baseline_id: "baseline-1",
          portfolio_id: "portfolio-1",
          system_id: "system-1",
          completed_at: "2026-07-30T00:00:00Z",
          candidate_model: { baseline_id: "baseline-1", source: {} },
        },
      },
    }, {}, { requireBaselineId: true });

    expect(parsed).toMatchObject({
      status: "completed",
      jobId: "job-1",
      datasetId: "dataset-1",
      baselineId: "baseline-1",
      portfolioId: "portfolio-1",
      systemId: "system-1",
      workspacePath: "/portfolio/portfolio-1/baselines/baseline-1",
      createdAt: "2026-07-30T00:00:00Z",
    });
  });

  it("fails immediately when a completed result has no baselineId", () => {
    expect(() => normalizeBaselineCreationResponse({
      status: "completed",
      jobId: "job-only",
      datasetId: "dataset-only",
      modelId: "must-not-be-used",
    }, {}, { requireBaselineId: true })).toThrow(BaselineCreationContractError);
  });

  it("never substitutes jobId, datasetId, modelId, or candidateId for baselineId", () => {
    const parsed = normalizeBaselineCreationResponse({
      status: "processing",
      jobId: "job-a",
      datasetId: "dataset-a",
      modelId: "model-a",
      candidateId: "candidate-a",
      candidate_model: { model_id: "model-a" },
    });
    expect(parsed.baselineId).toBeNull();
  });
});
