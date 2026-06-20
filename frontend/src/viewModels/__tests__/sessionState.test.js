import { describe, expect, it } from "vitest";

import { buildEmptySessionStore, buildSessionStore } from "../sessionState";

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
});
