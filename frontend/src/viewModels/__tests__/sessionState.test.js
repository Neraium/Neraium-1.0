import { describe, expect, it } from "vitest";

import {
  buildEmptySessionStore,
  buildLatestUploadSessionState,
  buildSessionStore,
  reconcileLatestUploadSessionState,
  resolveSessionStore,
} from "../sessionState";

function completedUpload(jobId = "job-terminal") {
  const result = {
    job_id: jobId,
    status: "COMPLETE",
    sii_reliable_enough_to_show: true,
    sii_intelligence: { facility_state: "Monitoring" },
  };
  return {
    snapshot: {
      job_id: jobId,
      status: "COMPLETE",
      processing_state: "complete",
      session_state: "verified",
      current_upload: { job_id: jobId, result },
      latest_result: result,
    },
    latest_result: result,
    session_state: "verified",
  };
}

describe("sessionState adapter", () => {
  it("starts in idle before any backend session payload is loaded", () => {
    expect(buildEmptySessionStore().uiState).toBe("idle");
  });

  it("maps explicit backend states into the frontend vocabulary", () => {
    expect(buildSessionStore({ session_state: "empty", snapshot: { status: "empty" } }).uiState).toBe("empty");
    expect(buildSessionStore({ session_state: "queued", snapshot: { status: "PENDING" } }).uiState).toBe("queued");
    expect(buildSessionStore({ session_state: "processing", snapshot: { status: "PROCESSING" } }).uiState).toBe("processing");
    expect(buildSessionStore({ session_state: "verified", snapshot: { status: "COMPLETE" }, latest_result: { job_id: "verified-job", engine_result: { overall_result: "stable" } } }).uiState).toBe("verified");
    expect(buildSessionStore({ session_state: "restored", snapshot: { status: "COMPLETE" }, latest_result: { job_id: "restored-job", engine_result: { overall_result: "stable" } } }).uiState).toBe("restored");
    expect(buildSessionStore({ session_state: "stale", snapshot: { status: "COMPLETE" } }).uiState).toBe("stale");
    expect(buildSessionStore({ session_state: "error", snapshot: { status: "FAILED" } }).uiState).toBe("error");
  });

  it("does not claim an active session without runtime data", () => {
    const session = buildSessionStore({
      session_state: "empty",
      snapshot: { status: "empty", latest_result: null },
    });
    expect(session.hasActiveSession).toBe(false);
    expect(session.hasRuntimeData).toBe(false);
  });

  it("builds a verified fallback store when App only has raw latest-upload payloads", () => {
    const session = resolveSessionStore({
      latestUploadSnapshot: { status: "COMPLETE", session_state: "verified", job_id: "job-42" },
      latestUploadResult: { job_id: "job-42", engine_result: { overall_result: "stable" } },
    });
    expect(session.uiState).toBe("verified");
    expect(session.jobId).toBe("job-42");
    expect(session.hasActiveSession).toBe(true);
  });

  it("maps terminal latest-upload status to verified even without a session_state field", () => {
    const session = buildSessionStore({
      snapshot: completedUpload("job-status-only").snapshot,
      latest_result: completedUpload("job-status-only").latest_result,
    });

    expect(session.uiState).toBe("verified");
    expect(session.isProcessing).toBe(false);
  });

  it.each(["COMPLETE", "COMPLETED", "SUCCESS", "SAVE_COMPLETE", "NAVIGATION_PENDING"])("maps %s terminal state to verified", (status) => {
    const payload = completedUpload(`job-${status.toLowerCase()}`);
    delete payload.session_state;
    delete payload.snapshot.session_state;
    payload.snapshot.status = status;

    expect(buildSessionStore(payload).uiState).toBe("verified");
  });

  it.each(["QUEUED", "PROCESSING", "WAITING"])("keeps a valid completion monotonic after stale %s for the same job", (status) => {
    const terminalState = buildLatestUploadSessionState(completedUpload());
    const staleResult = {
      ...terminalState.latestResult,
      status,
      processing_state: status.toLowerCase(),
    };
    const reconciliation = reconcileLatestUploadSessionState({
      terminalState,
      incomingPayload: {
        snapshot: {
          job_id: "job-terminal",
          status,
          processing_state: status.toLowerCase(),
          session_state: status === "QUEUED" ? "queued" : "processing",
          current_upload: { job_id: "job-terminal", result: staleResult },
        },
        latest_result: staleResult,
      },
    });

    expect(reconciliation.retainedTerminal).toBe(true);
    expect(reconciliation.snapshot.status).toBe("COMPLETE");
    expect(reconciliation.sessionStore.uiState).toBe("verified");
    expect(reconciliation.sessionStore.isProcessing).toBe(false);
  });

  it("retains terminal state through an empty eventual-consistency response", () => {
    const terminalState = buildLatestUploadSessionState(completedUpload());
    const reconciliation = reconcileLatestUploadSessionState({
      terminalState,
      incomingPayload: { snapshot: { status: "empty" }, latest_result: null, session_state: "empty" },
    });

    expect(reconciliation.retainedTerminal).toBe(true);
    expect(reconciliation.sessionStore.jobId).toBe("job-terminal");
  });

  it("accepts a different explicit job id as a new processing attempt", () => {
    const terminalState = buildLatestUploadSessionState(completedUpload());
    const reconciliation = reconcileLatestUploadSessionState({
      terminalState,
      incomingPayload: {
        snapshot: {
          job_id: "job-next",
          status: "PROCESSING",
          processing_state: "processing",
          session_state: "processing",
          current_upload: { job_id: "job-next" },
          state_available: true,
        },
        latest_result: null,
      },
    });

    expect(reconciliation.retainedTerminal).toBe(false);
    expect(reconciliation.terminalState).toBeNull();
    expect(reconciliation.sessionStore.jobId).toBe("job-next");
    expect(reconciliation.sessionStore.isProcessing).toBe(true);
  });
});
