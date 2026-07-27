import { describe, expect, it } from "vitest";

import { normalizeUploadJob } from "./uploadContract";
import {
  BASELINE_LEARN_STEPS,
  BASELINE_PROGRESS_STAGES,
  MONITORING_PROGRESS_STAGES,
  resolveWorkflowProgress,
} from "./workflowProgress";

describe("workflow progress separation", () => {
  it("uses the dedicated baseline stages and learn steps", () => {
    const progress = resolveWorkflowProgress({
      workflow: "create_baseline",
      payload: {
        job_type: "baseline_construction",
        baseline_stage: "learn",
        baseline_step: "building_behavioral_graph",
        baseline_step_label: "Building behavioral graph",
        baseline_learn_step_index: 6,
        processing_state: "baseline_behavioral_graph",
      },
    });

    expect(progress.kind).toBe("baseline");
    expect(progress.stages.map((stage) => stage.label)).toEqual(BASELINE_PROGRESS_STAGES.map((stage) => stage.label));
    expect(progress.learnSteps.map((step) => step.label)).toEqual(BASELINE_LEARN_STEPS.map((step) => step.label));
    expect(progress.current.detail).toBe("Building behavioral graph");
  });

  it("cannot mix monitoring labels into baseline progress", () => {
    const progress = resolveWorkflowProgress({
      workflow: "create_baseline",
      payload: {
        job_type: "baseline_construction",
        baseline_stage: "learn",
        baseline_step_label: "Comparing current behavior and preparing evidence",
        contract_stage: "structural_scoring",
        progress_label: "Comparing relationships",
      },
    });
    const visibleCopy = [
      ...progress.stages.flatMap((stage) => [stage.label, stage.description]),
      ...progress.learnSteps.map((step) => step.label),
      progress.current.detail,
    ].join(" ");

    expect(visibleCopy).not.toMatch(/current behavior|compare|comparing|comparison|anomaly|evidence|finding|drift against baseline/i);
    expect(progress.stages.map((stage) => stage.label)).not.toEqual(MONITORING_PROGRESS_STAGES.map((stage) => stage.label));
  });

  it("strips stale monitoring progress fields while normalizing baseline jobs", () => {
    const normalized = normalizeUploadJob({
      workflow: "create_baseline",
      job_type: "baseline_construction",
      status: "PROCESSING",
      processing_state: "baseline_relationships",
      baseline_stage: "learn",
      analysis_state: "comparison",
      contract_stage: "structural_scoring",
      contract_label: "Comparing current behavior",
      propagation_stage: "generating_findings_evidence",
      propagation_label: "Preparing evidence",
    });

    expect(normalized).not.toHaveProperty("analysis_state");
    expect(normalized).not.toHaveProperty("contract_stage");
    expect(normalized).not.toHaveProperty("propagation_stage");
    expect(normalized.message).toBe("Baseline construction is in progress.");
    expect(normalized.progress_state_machine).toBe("baseline_construction.v1");
  });

  it("keeps the full SII stages for monitoring jobs and ignores baseline fields", () => {
    const mixedPayload = {
      workflow: "analyze_new_data",
      job_type: "monitoring_analysis",
      contract_stage: "writing_state",
      baseline_stage: "learn",
      baseline_step_label: "Learning relationships",
    };
    const progress = resolveWorkflowProgress({
      workflow: "analyze_new_data",
      payload: mixedPayload,
    });
    const normalized = normalizeUploadJob(mixedPayload);

    expect(progress.kind).toBe("monitoring");
    expect(progress.stages.map((stage) => stage.label)).toEqual(MONITORING_PROGRESS_STAGES.map((stage) => stage.label));
    expect(progress.current.label).toBe("Evidence");
    expect(normalized).not.toHaveProperty("baseline_stage");
    expect(normalized).not.toHaveProperty("baseline_step_label");
  });
});
