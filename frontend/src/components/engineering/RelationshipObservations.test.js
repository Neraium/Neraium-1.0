import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import RelationshipObservations from "./RelationshipObservations";
import fixtures from "../../../tests/fixtures/presentation-phase1.json";
import fallbackCase from "../../../tests/fixtures/presentation-phase1-context-fallback.json";
import graphFallbackCase from "../../../tests/fixtures/presentation-phase1-graph-fallback.json";

afterEach(cleanup);

describe("relationship observation disclosure", () => {
  it.each(fixtures)("keeps case $case optional, collapsed, and separate from finding authority", ({ evidence }) => {
    const original = JSON.stringify(evidence);
    const { container } = render(React.createElement(RelationshipObservations, { evidence }));
    const disclosure = container.querySelector("details");
    expect(disclosure.open).toBe(false);
    fireEvent.click(screen.getByText("Show relationship evidence"));
    expect(screen.getByText(/Observed evidence is separate from a promoted finding/)).toBeTruthy();
    for (const label of ["Single-window change", "Temporal support established", "Persistent relationship change", "Recurrence supported", "Promoted changed edge", "General operating-mode match", "Source path in this result"]) expect(screen.getByText(label)).toBeTruthy();
    expect(container.textContent).toContain("unitless");
    expect(container.textContent).not.toMatch(/quantified consequence|observed magnitude|savings|loss|impact/i);
    expect(container.querySelectorAll("button,input,form")).toHaveLength(0);
    expect(JSON.stringify(evidence)).toBe(original);
  });

  it("does not render missing historical evidence or unversioned raw engine data", () => {
    const { container, rerender } = render(React.createElement(RelationshipObservations, {}));
    expect(container.textContent).toBe("");
    rerender(React.createElement(RelationshipObservations, { evidence: { observations: [{ error: "SECRET" }] } }));
    expect(container.textContent).toBe("");
  });

  it("preserves context limits and never renders unknown forensic fields", () => {
    const evidence = structuredClone(fixtures.find((item) => item.case === "D").evidence);
    evidence.observations[0].credentials = "CREDENTIAL_CANARY";
    evidence.observations[0].runtime_metadata = "RUNTIME_CANARY";
    const { container } = render(React.createElement(RelationshipObservations, { evidence }));
    expect(container.textContent).toContain("weak");
    expect(container.textContent).not.toContain("CANARY");
    expect(container.textContent).toContain("A specific gate reason is not inferred here");
  });

  it("shows recorded like-mode fallback beside a strong general match", () => {
    const evidence = structuredClone(fallbackCase.evidence);
    const original = JSON.stringify(evidence);
    const { container } = render(React.createElement(RelationshipObservations, { evidence }));
    expect(container.querySelector("details").open).toBe(false);
    for (const relationship of container.querySelectorAll(".relationship-observations > details")) {
      const facts = Object.fromEntries([...relationship.querySelectorAll(":scope > dl > div")].map((fact) => [fact.querySelector("dt").textContent, fact.querySelector("dd").textContent]));
      expect(facts["General operating-mode match"]).toBe("strong");
      expect(facts["Comparison basis"]).toBe("Global relationship model");
      expect(facts["Like-mode comparison status"]).toBe("Limited");
      expect(facts["Global fallback used"]).toBe("Yes");
      expect(facts["Comparison limitation"]).toBe("Too few recent samples in this operating mode.");
    }
    expect(container.textContent).not.toContain("insufficient_recent_mode_rows");
    expect(JSON.stringify(evidence)).toBe(original);
  });

  it("does not synthesize missing historical qualification or expose unknown reason strings", () => {
    const evidence = structuredClone(fixtures[0].evidence);
    const { container, rerender } = render(React.createElement(RelationshipObservations, { evidence }));
    expect(screen.queryByText("Comparison basis")).toBeNull();
    expect(screen.queryByText("Global fallback used")).toBeNull();
    evidence.comparison_qualification = { mode_conditioned_baseline: { used_global_fallback: true, fallback_reason: "RuntimeError SECRET_CANARY" } };
    rerender(React.createElement(RelationshipObservations, { evidence }));
    expect(screen.getByText("Comparison limitation").nextElementSibling.textContent).toBe("Not available");
    expect(container.textContent).not.toContain("SECRET_CANARY");
    expect(screen.queryByText("Like-mode comparison status")).toBeNull();
  });
});


it("qualifies retained global edges when dynamic comparison was unavailable", () => {
  const evidence = structuredClone(graphFallbackCase.evidence);
  evidence.diagnostics = { error: "RuntimeError SECRET_CANARY", traceback: "/internal/PATH_CANARY" };
  const original = JSON.stringify(evidence);
  const { container, rerender } = render(React.createElement(RelationshipObservations, { evidence }));
  expect(container.querySelector("details").open).toBe(false);
  for (const relationship of container.querySelectorAll(".relationship-observations > details")) {
    const facts = Object.fromEntries([...relationship.querySelectorAll(":scope > dl > div")].map((fact) => [fact.querySelector("dt").textContent, fact.querySelector("dd").textContent]));
    expect(facts["Comparison basis"]).toBe("Global relationship model");
    expect(facts["Comparison basis qualification"]).toBe("Dynamic relationship comparison was unavailable for this evaluation.");
    expect(facts["Promoted changed edge"]).toBe("Not recorded");
    expect(facts["Persistent relationship change"]).toBe("Not recorded");
  }
  expect(container.textContent).not.toMatch(/CANARY|RuntimeError|global_relationship_model_failure_fallback/);
  expect(container.querySelectorAll('[role="alert"],button,input,form')).toHaveLength(0);
  expect(JSON.stringify(evidence)).toBe(original);
  delete evidence.comparison_qualification.edge_basis;
  rerender(React.createElement(RelationshipObservations, { evidence }));
  expect(screen.queryByText("Comparison basis qualification")).toBeNull();
});
