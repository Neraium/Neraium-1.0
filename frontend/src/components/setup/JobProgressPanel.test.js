/* @vitest-environment jsdom */
import React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
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

  it("keeps the current operation visible and the detailed checklist collapsed by default", () => {
    const current = {
      id: "timestamp_quality",
      label: "Timestamp quality",
      status: "processing",
      completed_units: 0,
      total_units: 52_129,
      percent_complete: 0,
      unit_type: "rows",
      message: "Profiling timestamp and row quality.",
    };
    const job = uploadJob(current);
    job.job_progress.operations = [
      { id: "receiving", label: "Receiving file", status: "completed", percent_complete: 100 },
      current,
      { id: "signal_inventory", label: "Signal inventory", status: "pending", percent_complete: null },
    ];

    const { container } = render(React.createElement(JobProgressPanel, { uploadJob: job }));
    const panel = within(container);

    expect(panel.getAllByText("Timestamp quality").length).toBeGreaterThan(0);
    expect(panel.getByText("Profiling timestamp and row quality.")).toBeTruthy();
    const toggle = panel.getByRole("button", { name: "Processing details" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.getAttribute("aria-controls")).toBeTruthy();
    expect(panel.getByText("1 of 3 operations complete · Timestamp quality in progress")).toBeTruthy();
    expect(panel.queryByRole("list", { name: "Detailed backend operations" })).toBeNull();

    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const detail = panel.getByRole("list", { name: "Detailed backend operations" });
    expect(within(detail).getByText("Receiving file").closest("li").textContent).toContain("Complete");
    expect(within(detail).getByText("Signal inventory").closest("li").textContent).toContain("Pending");

    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
  });

  it("automatically exposes a failed operation", () => {
    const failed = {
      id: "learn_relationships",
      label: "Learn relationships",
      status: "failed",
      completed_units: 75,
      total_units: 190,
      percent_complete: 39,
      unit_type: "relationship_pairs",
      message: "Relationship learning could not continue.",
    };

    const { container } = render(React.createElement(JobProgressPanel, { uploadJob: uploadJob(failed) }));
    const panel = within(container);

    const toggle = panel.getByRole("button", { name: "Processing details" });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(panel.getByRole("list", { name: "Detailed backend operations" })).toBeTruthy();
    expect(panel.getByText("0 of 1 operations complete · Learn relationships failed")).toBeTruthy();
  });
});
