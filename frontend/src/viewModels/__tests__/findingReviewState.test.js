import { describe, expect, it } from "vitest";
import { reviewRecordFromFinding, reviewRecordFromWorkflow } from "../findingReviewState";


describe("finding workflow state", () => {
  it.each([
    ["open", "new"],
    ["acknowledged", "acknowledged"],
    ["investigating", "investigating"],
    ["monitoring", "monitoring"],
    ["resolved", "closed"],
    ["dismissed", "not_useful"],
  ])("maps persisted %s state without relying on feedback", (caseState, expected) => {
    expect(reviewRecordFromFinding({ caseState })).toMatchObject({ state: expected, persisted: true });
  });

  it("prefers the newest append-only case event", () => {
    const record = reviewRecordFromFinding({
      caseState: "open",
      caseHistory: [{
        state: "investigating",
        note: "Work order opened",
        recorded_at: "2026-07-20T09:00:00Z",
        actor: "engineer@example.com",
      }],
    });

    expect(record).toEqual({
      state: "investigating",
      reason: "Work order opened",
      note: "Work order opened",
      reviewedAt: "2026-07-20T09:00:00Z",
      owner: "engineer@example.com",
      persisted: true,
    });
  });

  it("retains the server workflow status and version for subsequent protected edits", () => {
    expect(reviewRecordFromWorkflow({
      findingId: "canonical-1",
      version: 7,
      status: "investigating",
      effectivePriority: "high",
    })).toMatchObject({
      state: "investigating",
      status: "investigating",
      version: 7,
      workflowFindingId: "canonical-1",
    });
  });
});
