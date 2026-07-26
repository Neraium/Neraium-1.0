import { describe, expect, it } from "vitest";

import {
  BASELINE_ANALYSIS_STATES,
  BASELINE_ANALYSIS_TRANSITIONS,
  CANONICAL_BACKEND_ANALYSIS_STATES,
  backendAnalysisState,
  canRenderCompletedAnalysis,
  completedAnalysisForDataset,
  resolveBaselineAnalysisState,
} from "./baselineAnalysisState";

const selectedFile = { name: "current.csv", size: 128 };
const completedAnalysis = {
  status: "complete",
  systems: [{ id: "system-1" }],
  insights: [{ id: "finding-1" }],
  fingerprint: { drift_status: "changed", confidence: "high" },
};

function backendPayload(datasetId, analysisState, analysisResult = null) {
  return {
    dataset_id: datasetId,
    job_id: datasetId,
    analysis_state: analysisState,
    analysis_result: analysisResult,
  };
}

describe("baseline onboarding canonical state machine", () => {
  it("defines every backend analysis state in the audited workflow", () => {
    expect(CANONICAL_BACKEND_ANALYSIS_STATES).toEqual([
      "no_dataset",
      "dataset_selected",
      "upload_complete",
      "ready_to_analyze",
      "analysis_queued",
      "validating",
      "mapping",
      "baseline_creation",
      "comparison",
      "evidence_generation",
      "completed",
      "failed",
      "cancelled",
    ]);
  });

  it("supports the full fresh-analysis transition path", () => {
    const states = [
      "no_dataset",
      "dataset_selected",
      "ready_to_analyze",
      "uploading",
      "upload_complete",
      "analysis_queued",
      "validating",
      "mapping",
      "baseline_creation",
      "comparison",
      "evidence_generation",
      "completed",
      "no_dataset",
      "dataset_selected",
      "ready_to_analyze",
      "uploading",
      "upload_complete",
      "analysis_queued",
      "validating",
      "mapping",
      "baseline_creation",
      "comparison",
      "evidence_generation",
      "completed",
    ];

    states.slice(0, -1).forEach((state, index) => {
      expect(BASELINE_ANALYSIS_TRANSITIONS[state]).toContain(states[index + 1]);
    });
    expect(BASELINE_ANALYSIS_TRANSITIONS.evidence_generation).toEqual(expect.arrayContaining(["completed", "failed", "cancelled"]));
  });

  it("never derives backend completion from legacy complete fields", () => {
    expect(backendAnalysisState({ status: "COMPLETE", processing_state: "complete", result_available: true })).toBeNull();
    expect(backendAnalysisState({ analysis_state: "completed" })).toBe("completed");
  });

  it("always resolves no dataset before considering stale completed state", () => {
    expect(resolveBaselineAnalysisState({
      selectedFiles: [],
      uploadState: "complete",
      activeDatasetId: "old-job",
      uploadJob: backendPayload("old-job", "completed", completedAnalysis),
    })).toBe(BASELINE_ANALYSIS_STATES.NO_DATASET);
  });

  it("rejects a completed result belonging to another dataset", () => {
    const stale = backendPayload("old-job", "completed", completedAnalysis);
    expect(completedAnalysisForDataset("new-job", stale)).toBeNull();
    expect(canRenderCompletedAnalysis({
      analysisState: "completed",
      activeDatasetId: "new-job",
      selectedFiles: [selectedFile],
      analysisResult: completedAnalysisForDataset("new-job", stale),
    })).toBe(false);
  });

  it("renders completion only for the selected dataset and a completed AnalysisResult", () => {
    const current = backendPayload("current-job", "completed", completedAnalysis);
    const result = completedAnalysisForDataset("current-job", current);
    expect(result).toBe(completedAnalysis);
    expect(completedAnalysisForDataset("current-job", { ...current, analysis_state: undefined, status: "COMPLETE" })).toBeNull();
    expect(completedAnalysisForDataset("current-job", { analysis_state: "completed", analysis_result: completedAnalysis })).toBeNull();
    expect(canRenderCompletedAnalysis({
      analysisState: "completed",
      activeDatasetId: "current-job",
      selectedFiles: [selectedFile],
      analysisResult: result,
    })).toBe(true);
    expect(canRenderCompletedAnalysis({
      analysisState: "evidence_generation",
      activeDatasetId: "current-job",
      selectedFiles: [selectedFile],
      analysisResult: result,
    })).toBe(false);
  });

  it("treats a newly selected dataset as fresh even when an old completed job exists", () => {
    expect(resolveBaselineAnalysisState({
      selectedFiles: [selectedFile],
      uploadState: "validated",
      activeDatasetId: null,
      uploadJob: backendPayload("old-job", "completed", completedAnalysis),
    })).toBe(BASELINE_ANALYSIS_STATES.READY_TO_ANALYZE);
  });
});
