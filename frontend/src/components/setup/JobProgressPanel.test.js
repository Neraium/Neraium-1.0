/* @vitest-environment jsdom */
import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import JobProgressPanel from "./JobProgressPanel";

function uploadJob(operation) {
  return {
    execution_state: "processing",
    job_progress: {
      contract_version: "job-progress.v1",
      status: "processing",
      substage: operation.id,
      message: operation.message,
      overall_percent_complete: 72,
      elapsed_seconds: 18,
      seconds_since_update: 1,
      last_worker_heartbeat_at: "2026-08-09T12:00:17Z",
      seconds_since_worker_heartbeat: 1,
      updated_at: "2026-08-09T12:00:17Z",
      workflow_steps: [
        {
          id: "analysis",
          label: "Analyze",
          status: "processing",
          percent_complete: 72,
        },
      ],
      operations: [operation],
    },
  };
}

describe("JobProgressPanel operation progress", () => {
  it("switches between indeterminate and measurable operation states without inventing a percentage", () => {
    const { rerender } = render(
      React.createElement(JobProgressPanel, {
        uploadJob: uploadJob({
          id: "evidence_fusion",
          label: "Evidence generation",
          status: "processing",
          completed_units: 7,
          total_units: null,
          percent_complete: null,
          unit_type: "evidence_candidates",
          message: "Discovering eligible evidence candidates from completed modules.",
        }),
      }),
    );

    expect(screen.getByText("Measuring work")).toBeTruthy();
    expect(screen.getByText("Measuring work · Processing")).toBeTruthy();
    expect(screen.getByText("Discovering eligible evidence candidates from completed modules.")).toBeTruthy();
    expect(screen.getByText("7 evidence candidates processed")).toBeTruthy();
    expect(screen.queryByText("0%")).toBeNull();
    expect(screen.getAllByRole("progressbar")).toHaveLength(1);
    expect(screen.getByRole("progressbar", { name: "Overall backend workflow" }).getAttribute("aria-valuenow")).toBe("72");

    rerender(
      React.createElement(JobProgressPanel, {
        uploadJob: uploadJob({
          id: "evidence_fusion",
          label: "Evidence generation",
          status: "processing",
          completed_units: 8,
          total_units: 20,
          percent_complete: 40,
          unit_type: "evidence_candidates",
          message: "Organized 8 of 20 evidence candidates.",
        }),
      }),
    );

    expect(screen.getAllByText("40%").length).toBeGreaterThan(0);
    expect(screen.queryByText("Measuring work")).toBeNull();
    expect(screen.getAllByRole("progressbar")).toHaveLength(2);
    expect(screen.getByRole("progressbar", { name: "Evidence generation" }).getAttribute("aria-valuenow")).toBe("40");
    expect(screen.getByText("8 / 20 evidence candidates")).toBeTruthy();
  });
});
