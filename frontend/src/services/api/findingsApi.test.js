import { describe, expect, it, vi } from "vitest";
import { FindingApiError, fetchFinding, fetchFindingActivity, fetchFindings, patchFindingWorkflow, postFindingFeedback, resolveFinding } from "./findingsApi";

function response(payload, { ok = true, status = 200 } = {}) {
  return { ok, status, json: async () => payload };
}

describe("findings API", () => {
  it("loads workflow and activity without conflating analytical evidence", async () => {
    const apiFetch = vi.fn()
      .mockResolvedValueOnce(response({ finding: { id: "finding/1", evidence: { immutable: true }, workflow: { version: 3, status: "investigating", effective_priority: "high" } } }))
      .mockResolvedValueOnce(response({ events: [{ event_id: "event-1", version: 3 }] }));
    await expect(fetchFinding({ apiFetch, findingId: "finding/1" })).resolves.toMatchObject({ workflow: { findingId: "finding/1", version: 3, status: "investigating", priority: "high" } });
    await expect(fetchFindingActivity({ apiFetch, findingId: "finding/1" })).resolves.toEqual([{ event_id: "event-1", version: 3 }]);
    expect(apiFetch.mock.calls[0][0]).toBe("/api/findings/finding%2F1");
    expect(apiFetch.mock.calls[1][0]).toBe("/api/findings/finding%2F1/activity");
  });

  it("lists canonical findings for an evidence run", async () => {
    const apiFetch = vi.fn().mockResolvedValue(response({ findings: [{ finding_id: "canonical-1", source: { kind: "evidence_run", id: "run-42", finding_key: "source-1" }, evidence: { id: "source-1" }, workflow: { version: 0, status: "open", effective_priority: "medium" } }], limit: 100, offset: 0, has_more: false }));
    const result = await fetchFindings({ apiFetch, sourceKind: "evidence_run", sourceRunId: "run-42" });
    expect(result.findings[0]).toMatchObject({ workflow: { findingId: "canonical-1", source: { finding_key: "source-1" } } });
    expect(apiFetch.mock.calls[0][0]).toBe("/api/findings?source_kind=evidence_run&source_run_id=run-42&limit=100&offset=0");
  });

  it("sends assignment edits with explicit version protection", async () => {
    const apiFetch = vi.fn().mockResolvedValue(response({ finding_id: "finding-1", workflow: { version: 8, status: "investigating", assignment: { target_type: "team", label: "Mechanical", external_ref: "CMMS-72" }, effective_priority: "critical" } }));
    const result = await patchFindingWorkflow({ apiFetch, findingId: "finding-1", expectedVersion: 7, idempotencyKey: "edit-7", changes: { status: "investigating", priority: "critical", dueDate: "2026-08-18", managerNote: "Check on day shift", assignment: { kind: "team", label: "Mechanical", externalReference: "CMMS-72" } } });
    expect(result.workflow).toMatchObject({ version: 8, assignment: { kind: "team", label: "Mechanical", externalReference: "CMMS-72" } });
    expect(apiFetch).toHaveBeenCalledWith("/api/findings/finding-1/workflow", expect.objectContaining({
      method: "PATCH",
      headers: { "Content-Type": "application/json", "If-Match": "7" },
      body: JSON.stringify({ expected_version: 7, idempotency_key: "edit-7", status: "investigating", user_priority: "critical", due_at: "2026-08-18", manager_note: "Check on day shift", assignment: { target_type: "team", label: "Mechanical", external_ref: "CMMS-72" } }),
    }));
  });

  it("sends resolution outcome and note without a second workflow write", async () => {
    const apiFetch = vi.fn().mockResolvedValue(response({ workflow: { version: 5, status: "resolved", resolution: { outcome: "maintenance_performed", note: "Seal replaced" } } }));
    await expect(resolveFinding({ apiFetch, findingId: "finding-1", expectedVersion: 4, idempotencyKey: "resolve-4", outcome: "maintenance_performed", note: "Seal replaced" })).resolves.toMatchObject({ workflow: { version: 5, resolution: { outcome: "maintenance_performed", note: "Seal replaced" } } });
    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual({ expected_version: 4, idempotency_key: "resolve-4", outcome: "maintenance_performed", note: "Seal replaced" });
  });

  it("records finding feedback against the same versioned sidecar", async () => {
    const apiFetch = vi.fn().mockResolvedValue(response({ finding_id: "finding-1", workflow: { version: 6, status: "monitoring", latest_feedback: { category: "useful_warning" } } }));
    await postFindingFeedback({ apiFetch, findingId: "finding-1", expectedVersion: 5, idempotencyKey: "feedback-5", category: "useful_warning", note: "Watch next load cycle", actionTaken: "Reviewed logs" });
    expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual({ expected_version: 5, idempotency_key: "feedback-5", category: "useful_warning", note: "Watch next load cycle", outcome: null, action_taken: "Reviewed logs", intervention_at: null, followup_at: null });
  });

  it("surfaces version conflicts distinctly", async () => {
    const apiFetch = vi.fn().mockResolvedValue(response({ detail: { code: "version_conflict", message: "Workflow changed since it was loaded." } }, { ok: false, status: 409 }));
    await expect(patchFindingWorkflow({ apiFetch, findingId: "finding-1", expectedVersion: 2, changes: { priority: "high" } })).rejects.toMatchObject({
      name: "FindingApiError",
      conflict: true,
      status: 409,
      message: "Workflow changed since it was loaded.",
    });
  });

  it("reads the backend stale-version error shape without stringifying its detail", async () => {
    const apiFetch = vi.fn().mockResolvedValue(response({ detail: { error: "stale_workflow_version", current_version: 9 } }, { ok: false, status: 409 }));
    await expect(patchFindingWorkflow({ apiFetch, findingId: "finding-1", expectedVersion: 2, changes: { priority: "high" } })).rejects.toMatchObject({
      conflict: true,
      code: "stale_workflow_version",
      message: "stale_workflow_version",
      payload: { detail: { current_version: 9 } },
    });
  });

  it("requires a version before a mutation is attempted", async () => {
    const apiFetch = vi.fn();
    await expect(resolveFinding({ apiFetch, findingId: "finding-1", outcome: "confirmed_issue" })).rejects.toBeInstanceOf(TypeError);
    expect(apiFetch).not.toHaveBeenCalled();
    expect(new FindingApiError("missing", { status: 404 }).unavailable).toBe(true);
  });
});
