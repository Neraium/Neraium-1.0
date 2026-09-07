import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import GovernanceLayer from "./GovernanceLayer";

afterEach(cleanup);

it.each(["Observed", "Persistent", "Corroborated", "Characterized", "Context-qualified"])("renders backend maturity %s in plain language", (label) => {
  render(React.createElement(GovernanceLayer, { governance: { schema_version: "runtime-governance-v1", maturity_label: label, authority_label: "Observation only", context_label: "External context unavailable" } }));
  expect(screen.getByText(label)).toBeTruthy();
  expect(screen.getByText("Observation only")).toBeTruthy();
  expect(screen.queryByText(/L[0-4]/)).toBeNull();
  expect(screen.queryByRole("button")).toBeNull();
});

it("does not infer maturity or authority from confidence, consequence, or human approval", () => {
  render(React.createElement(GovernanceLayer, { governance: { schema_version: "runtime-governance-v1", confidence: 1, consequence: { value: 999 }, human_review: { status: "approved" }, maturity: { level: "L4" } } }));
  expect(screen.queryByText("Context-qualified")).toBeNull();
  expect(screen.queryByText(/Permitted|Approved|Activate/)).toBeNull();
  expect(screen.getAllByText("Unavailable").length).toBe(3);
});

it("keeps audit facts behind progressive disclosure", () => {
  const { container } = render(React.createElement(GovernanceLayer, { audit: true, governance: { schema_version: "runtime-governance-v1", maturity_label: "Persistent", source_run_id: "run-123", evaluated_at: "2026-09-07T12:00:00Z", limitations: ["Rate assessment unavailable"] } }));
  expect(screen.getByText("Governance audit")).toBeTruthy();
  expect(container.querySelector("details").open).toBe(false);
  expect(screen.queryByRole("button")).toBeNull();
});

it("preserves historical UI without governance", () => {
  const { container } = render(React.createElement(GovernanceLayer));
  expect(container.textContent).toBe("");
});
