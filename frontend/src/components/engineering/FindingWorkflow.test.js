/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import FindingWorkflowPanel, { FindingWorkflowSummary } from "./FindingWorkflow";

const WORKFLOW = {
  findingId: "canonical-finding-1",
  version: 4,
  status: "investigating",
  priority: "high",
  userPriority: "high",
  dueDate: "2026-08-20T23:59:59Z",
  managerNote: "Inspect during day shift",
  assignment: { kind: "team", label: "Mechanical", externalReference: "TEAM-7" },
  workOrderReference: "WO-42",
  validationOutcome: "pending_field_check",
  persisted: true,
};

afterEach(cleanup);

describe("finding workflow UI", () => {
  it("summarizes effective priority, assignment, due state, and lifecycle independently", () => {
    render(React.createElement(FindingWorkflowSummary, { workflow: WORKFLOW }));
    expect(screen.getByText("High")).toBeTruthy();
    expect(screen.getByText("Mechanical")).toBeTruthy();
    expect(screen.getByText("Investigating")).toBeTruthy();
    expect(screen.getByText("Pending Field Check")).toBeTruthy();
    expect(screen.getByText("WO-42")).toBeTruthy();
  });

  it("submits assignment and workflow fields against the displayed version", async () => {
    const onSave = vi.fn().mockResolvedValue({});
    render(React.createElement(FindingWorkflowPanel, { finding: { id: "source-1" }, workflow: WORKFLOW, onSave }));
    fireEvent.click(screen.getByText("Edit workflow"));
    fireEvent.change(screen.getByLabelText("User priority"), { target: { value: "critical" } });
    fireEvent.change(screen.getByLabelText("Assign to"), { target: { value: "person" } });
    fireEvent.change(screen.getByLabelText("Person or team label"), { target: { value: "Engineer Two" } });
    fireEvent.change(screen.getByLabelText("Assignment external reference"), { target: { value: "DIR-88" } });
    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-08-22" } });
    fireEvent.change(screen.getByLabelText("Manager note"), { target: { value: "Validate on start-up" } });
    fireEvent.change(screen.getByLabelText("Work order reference"), { target: { value: "WO-99" } });
    fireEvent.change(screen.getByLabelText("External reference"), { target: { value: "CASE-3" } });
    fireEvent.change(screen.getByLabelText("Validation outcome"), { target: { value: "confirmed" } });
    fireEvent.change(screen.getByLabelText("Validation note"), { target: { value: "Field check complete" } });
    fireEvent.click(screen.getByRole("button", { name: "Save workflow" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({
      findingId: "canonical-finding-1",
      expectedVersion: 4,
      changes: {
        status: "investigating",
        priority: "critical",
        assignment: { kind: "person", label: "Engineer Two", externalReference: "DIR-88" },
        dueDate: "2026-08-22T23:59:59Z",
        managerNote: "Validate on start-up",
        workOrderReference: "WO-99",
        externalReference: "CASE-3",
        validationOutcome: "confirmed",
        validationNote: "Field check complete",
      },
    }));
  });

  it("records controlled feedback and resolution outcomes", async () => {
    const onFeedback = vi.fn().mockResolvedValue({});
    const onResolve = vi.fn().mockResolvedValue({});
    render(React.createElement(FindingWorkflowPanel, { finding: { id: "source-1" }, workflow: WORKFLOW, onFeedback, onResolve }));
    fireEvent.click(screen.getByText("Record feedback"));
    fireEvent.change(screen.getByLabelText("Feedback category"), { target: { value: "sensor_or_data_problem" } });
    fireEvent.change(screen.getByLabelText("Feedback note"), { target: { value: "Signal intermittently flat" } });
    fireEvent.change(screen.getByLabelText("Action taken"), { target: { value: "Compared redundant sensor" } });
    fireEvent.click(screen.getByRole("button", { name: "Save feedback" }));
    await waitFor(() => expect(onFeedback).toHaveBeenCalledWith(expect.objectContaining({ findingId: "canonical-finding-1", expectedVersion: 4, category: "sensor_or_data_problem" })));

    fireEvent.click(screen.getByText("Record resolution"));
    const resolutionSection = screen.getByText("Record resolution").closest("details");
    fireEvent.change(within(resolutionSection).getByLabelText("Resolution outcome"), { target: { value: "maintenance_performed" } });
    fireEvent.change(within(resolutionSection).getByLabelText("Resolution note"), { target: { value: "Transmitter replaced" } });
    fireEvent.click(within(resolutionSection).getByRole("button", { name: "Resolve finding" }));
    await waitFor(() => expect(onResolve).toHaveBeenCalledWith({ findingId: "canonical-finding-1", expectedVersion: 4, outcome: "maintenance_performed", note: "Transmitter replaced" }));
    expect(within(resolutionSection).queryByRole("option", { name: "Maintenance completed" })).toBeNull();
  });

  it("blocks blind retry after a version conflict and offers reload", async () => {
    const conflict = Object.assign(new Error("stale"), { status: 409, conflict: true });
    const onSave = vi.fn().mockRejectedValue(conflict);
    const onReload = vi.fn();
    render(React.createElement(FindingWorkflowPanel, { finding: { id: "source-1" }, workflow: WORKFLOW, onSave, onReload }));
    fireEvent.click(screen.getByText("Edit workflow"));
    fireEvent.click(screen.getByRole("button", { name: "Save workflow" }));
    expect(await screen.findByText("This finding changed after you opened it. Reload the workflow before saving again.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Reload workflow" }));
    expect(onReload).toHaveBeenCalledTimes(1);
  });
});
