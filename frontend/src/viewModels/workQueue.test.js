import { describe, expect, it } from "vitest";
import { emptyStateForQueue, normalizeWorkFinding, queryForWorkQueue, workDueState } from "./workQueue";

function canonicalItem(assignment = { target_type: "person", label: "Taylor Tech", external_ref: "tech@example.com" }) {
  return {
    finding: {
      finding_id: "finding-1",
      source: { finding_key: "condition-1", run_id: "run-1" },
      evidence: { finding: { headline: "Supply fan coupling weakened", system_name: "Air system", equipment_name: "AHU 1", next_checks: ["Inspect the fan belt."], confidence: "high" } },
    },
    workflow: { findingId: "finding-1", version: 4, status: "investigating", priority: "critical", assignment, assignedBy: "lead@example.com", dueDate: "2020-01-01T00:00:00Z" },
  };
}

describe("work queue view model", () => {
  it("maps My Work and queue filters to server-authored parameters", () => {
    expect(queryForWorkQueue({ mode: "mine", filter: "overdue", limit: 30, offset: 30 })).toMatchObject({ assignedToMe: true, overdue: true, active: false, limit: 30, offset: 30 });
    expect(queryForWorkQueue({ mode: "mine", filter: "needs-assignment" })).toMatchObject({ assignedToMe: false, unassigned: true });
    expect(queryForWorkQueue({ mode: "team", filter: "needs-assignment", assignee: "tech@example.com" })).toMatchObject({ assignedToMe: false, unassigned: true, assignee: "tech@example.com" });
  });

  it("prioritizes operational card language and preserves historical assignments", () => {
    const current = normalizeWorkFinding(canonicalItem(), new Date("2026-08-12T12:00:00Z"));
    expect(current).toMatchObject({ equipment: "AHU 1", system: "Air system", priority: "critical", statusLabel: "In progress", confidence: "High", assignedBy: "lead@example.com" });
    expect(current.change).toBe("Supply fan response weakened");
    expect(current.change).not.toMatch(/coupling|relationship|signal id/i);
    expect(current.due.overdue).toBe(true);

    const historical = normalizeWorkFinding(canonicalItem({ target_type: "person", label: "Former technician", external_ref: null }));
    expect(historical.assignment).toMatchObject({ label: "Former technician", historical: true, externalReference: "" });
  });

  it("derives overdue and requested empty states", () => {
    expect(workDueState("2026-08-11", new Date("2026-08-12T12:00:00Z"))).toMatchObject({ overdue: true, tone: "overdue" });
    expect(emptyStateForQueue({ mode: "mine", filter: "active" }).title).toBe("Nothing assigned to you");
    expect(emptyStateForQueue({ mode: "team", filter: "needs-assignment" }).title).toBe("No unassigned findings");
    expect(emptyStateForQueue({ mode: "team", filter: "recently-resolved" }).title).toBe("No recently resolved findings");
  });
});
