import { describe, expect, it } from "vitest";

import { authoritativeJobState, isPollableJobState, isTerminalJobState, jobStateLabel } from "../uploadJobState";

describe("authoritative upload job state", () => {
  it.each([
    [{ status: "PENDING", processing_state: "queued", worker_state: "running", queue_state: "pending" }, "queued"],
    [{ status: "PENDING", processing_state: "queued", worker_claimed: true, queue_state: "processing" }, "claimed"],
    [{ status: "PROCESSING", processing_state: "baseline_relationship_learning", worker_claimed: true }, "processing"],
    [{ status: "PROCESSING", processing_state: "baseline_relationship_learning", worker_heartbeat_stale: true }, "stalled"],
    [{ status: "COMPLETE", processing_state: "complete", job_state: "completed" }, "completed"],
    [{ status: "FAILED", processing_state: "failed", job_state: "failed" }, "failed"],
    [{ job_id: "waiting-job", poll_connection_state: "interrupted" }, "waiting"],
    [{ status: "COMPLETE", job_state: "completed", execution_state: "processing" }, "completed"],
    [{ status: "PROCESSING", queue_state: "pending", execution_state: "processing", worker_state: "running" }, "queued"],
    [{ status: "PROCESSING", execution_state: "processing", worker_state: "running", worker_heartbeat_stale: true }, "stalled"],
    [{ status: "ACCEPTED", processing_state: "accepted" }, "queued"],
    [{}, "idle"],
  ])("maps backend evidence %# to %s", (payload, expected) => {
    expect(authoritativeJobState(payload)).toBe(expected);
  });

  it("does not treat polling or an unclaimed worker heartbeat as processing", () => {
    expect(authoritativeJobState({
      job_id: "queued-job",
      status: "PENDING",
      processing_state: "queued",
      worker_state: "running",
      poll_connection_state: "connected",
    })).toBe("queued");
  });

  it("classifies lifecycle actions", () => {
    expect(isPollableJobState("claimed")).toBe(true);
    expect(isPollableJobState("completed")).toBe(false);
    expect(isTerminalJobState("failed")).toBe(true);
    expect(jobStateLabel("stalled")).toBe("Stalled");
  });
});
