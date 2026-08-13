/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import WorkQueueWorkspace from "./WorkQueueWorkspace";

function response(payload, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

function casePayload(workflowOverrides = {}) {
  return {
    finding_id: "finding-1",
    source: { kind: "evidence_run", id: "run-1", finding_key: "condition-1", run_id: "run-1" },
    evidence: { finding: { headline: "Supply fan coupling weakened", system_name: "Air system", equipment_name: "AHU 1", next_checks: ["Inspect the fan belt first."], confidence: "high" } },
    workflow: {
      version: 1,
      status: "open",
      effective_priority: "high",
      assignment: { target_type: "person", label: "Taylor Tech", external_ref: "tech@example.com" },
      assigned_by: "Morgan Lead",
      due_at: "2026-08-14T23:59:59Z",
      latest_field_report: null,
      ...workflowOverrides,
    },
    activity: { count: 1 },
    created_at: "2026-08-12T09:00:00Z",
  };
}

function apiHarness(initialCase = casePayload()) {
  let current = initialCase;
  const apiFetch = vi.fn(async (url, options = {}) => {
    const path = String(url);
    if (path === "/api/findings/members") return response({ members: [{ member_id: "tech@example.com", display_name: "Taylor Tech", role: "viewer", is_active: true }, { member_id: "lead@example.com", display_name: "Morgan Lead", role: "operator", is_active: true }] });
    if (path.endsWith("/activity")) return response({ activity: [{ label: "Finding assigned", summary: "Assigned to Taylor Tech.", actor: "Morgan Lead", recorded_at: "2026-08-12T10:00:00Z", version: 1 }], events: [{ event_type: "workflow_updated", changes: { assignment: { label: "Taylor Tech" } } }] });
    if (path.endsWith("/workflow") && options.method === "PATCH") {
      const body = JSON.parse(options.body);
      current = { ...current, workflow: { ...current.workflow, version: current.workflow.version + 1, status: body.status ?? current.workflow.status, effective_priority: body.user_priority ?? current.workflow.effective_priority, due_at: body.due_at ?? current.workflow.due_at, assignment: body.assignment === undefined ? current.workflow.assignment : body.assignment, assigned_by: "lead@example.com" } };
      return response(current);
    }
    if (path.endsWith("/field-reports") && options.method === "POST") {
      const body = JSON.parse(options.body);
      current = { ...current, workflow: { ...current.workflow, version: current.workflow.version + 1, status: body.investigation_complete ? "awaiting_review" : current.workflow.status, latest_field_report: { ...body, actor: "tech@example.com", recorded_at: "2026-08-12T11:00:00Z" } } };
      return response(current);
    }
    if (path.includes("/resolution") && options.method === "POST") {
      current = { ...current, workflow: { ...current.workflow, version: current.workflow.version + 1, status: "resolved" } };
      return response(current);
    }
    if (path.startsWith("/api/findings?")) return response({ findings: [current], limit: 30, offset: 0, has_more: false });
    if (path === "/api/findings/finding-1") return response(current);
    return response({}, 404);
  });
  return apiFetch;
}

afterEach(cleanup);

describe("shared maintenance Work area", () => {
  it("gives an assigned technician a plain-language, actionable field workflow", async () => {
    const apiFetch = apiHarness();
    render(React.createElement(WorkQueueWorkspace, { apiFetch, currentUser: { email: "tech@example.com", name: "Taylor Tech", role: "viewer" } }));
    const card = await screen.findByTestId("work-finding-card");
    expect(within(card).getByRole("heading", { name: "AHU 1" })).toBeTruthy();
    expect(within(card).getByText("Supply fan response weakened")).toBeTruthy();
    expect(card.textContent).not.toMatch(/coupling|raw signal|provenance|lineage/i);
    for (const label of ["Status", "Assigned to", "Due", "Change confidence"]) expect(within(card).getByText(label)).toBeTruthy();

    fireEvent.click(within(card).getByRole("button", { name: /Open AHU 1/i }));
    expect(await screen.findByRole("heading", { name: "Report what you found" })).toBeTruthy();
    expect(screen.getByText("Inspect the fan belt first.")).toBeTruthy();
    expect(screen.getByText("Morgan Lead")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Accept work" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Accept work" }));
    await waitFor(() => expect(apiFetch.mock.calls.some(([url, options]) => String(url).endsWith("/workflow") && JSON.parse(options.body).status === "acknowledged")).toBe(true));

    fireEvent.change(screen.getByLabelText("What did you inspect?"), { target: { value: "Fan belt and bearings" } });
    fireEvent.change(screen.getByLabelText("What did you find?"), { target: { value: "Belt was loose" } });
    fireEvent.click(screen.getByLabelText("Yes"));
    fireEvent.click(screen.getByLabelText("My investigation is complete"));
    fireEvent.click(screen.getByRole("button", { name: "Send for review" }));
    await waitFor(() => expect(apiFetch.mock.calls.some(([url]) => String(url).endsWith("/field-reports"))).toBe(true));
    const reportCall = apiFetch.mock.calls.find(([url]) => String(url).endsWith("/field-reports"));
    expect(JSON.parse(reportCall[1].body)).toMatchObject({ inspected: "Fan belt and bearings", found: "Belt was loose", problem_found: "yes", investigation_complete: true });
    expect(await screen.findByText("Latest field report")).toBeTruthy();
  });

  it("uses member identities for lead assignment and keeps filters server-authored", async () => {
    const apiFetch = apiHarness(casePayload({ assignment: null }));
    render(React.createElement(WorkQueueWorkspace, { apiFetch, currentUser: { email: "lead@example.com", name: "Morgan Lead", role: "operator" } }));
    await screen.findByTestId("work-finding-card");
    fireEvent.click(screen.getByRole("button", { name: "Team Findings" }));
    fireEvent.click(screen.getByRole("button", { name: "Needs assignment" }));
    await waitFor(() => expect(apiFetch.mock.calls.some(([url]) => String(url).includes("unassigned=true"))).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: /Open AHU 1/i }));
    const leadControls = (await screen.findByRole("heading", { name: "Ownership and next step" })).closest("section");
    const picker = within(leadControls).getByLabelText("Assign to");
    fireEvent.change(picker, { target: { value: "tech@example.com" } });
    fireEvent.change(within(leadControls).getByLabelText("Priority"), { target: { value: "critical" } });
    fireEvent.click(within(leadControls).getByRole("button", { name: "Save assignment" }));
    await waitFor(() => expect(apiFetch.mock.calls.some(([url]) => String(url).endsWith("/workflow"))).toBe(true));
    const patchCall = apiFetch.mock.calls.find(([url]) => String(url).endsWith("/workflow"));
    expect(JSON.parse(patchCall[1].body)).toMatchObject({ assignment: { target_type: "person", label: "Taylor Tech", external_ref: "tech@example.com" }, user_priority: "critical" });
  });

  it("renders human activity, technician-note and evidence availability states", async () => {
    const apiFetch = apiHarness();
    const onOpenInvestigation = vi.fn();
    render(React.createElement(WorkQueueWorkspace, { apiFetch, currentUser: { email: "lead@example.com", role: "operator" }, technicalFindingFor: () => ({ id: "condition-1" }), onOpenInvestigation }));
    fireEvent.click(await screen.findByRole("button", { name: /Open AHU 1/i }));
    expect(await screen.findByText("Finding assigned")).toBeTruthy();
    expect(screen.getByText("Assigned to Taylor Tech.")).toBeTruthy();
    expect(screen.queryByText("workflow_updated")).toBeNull();
    expect(screen.getByText("No technician notes yet.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open investigation" }));
    expect(onOpenInvestigation).toHaveBeenCalledWith({ id: "condition-1" });
  });

  it("shows concise queue-specific empty states", async () => {
    const apiFetch = vi.fn(async (url) => String(url) === "/api/findings/members" ? response({ members: [] }) : response({ findings: [], has_more: false }));
    render(React.createElement(WorkQueueWorkspace, { apiFetch, currentUser: { email: "lead@example.com", role: "operator" } }));
    expect(await screen.findByRole("heading", { name: "Nothing assigned to you" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Team Findings" }));
    fireEvent.click(screen.getByRole("button", { name: "Overdue" }));
    expect(await screen.findByRole("heading", { name: "No overdue work" })).toBeTruthy();
  });
});
