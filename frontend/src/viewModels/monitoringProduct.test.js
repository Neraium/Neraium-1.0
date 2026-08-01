/* @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import {
  buildFindingNotification,
  filterFindings,
  normalizePersistedFinding,
  persistenceLabel,
} from "./monitoringProduct";

describe("monitoring product compatibility", () => {
  it("does not surface completed analysis as a finding without a meaningful change", () => {
    expect(normalizePersistedFinding({
      run_id: "quiet",
      status: "complete",
      observation_status: "normal",
      evidence_summary: ["Analysis complete."],
    })).toBeNull();
  });

  it("withholds unreliable or insufficient records", () => {
    expect(normalizePersistedFinding({ run_id: "withheld", meaningful_change: true, status: "complete", confidence_tier: "Withheld" })).toBeNull();
    expect(normalizePersistedFinding({ run_id: "unreliable", meaningful_change: true, status: "complete", reliable: false })).toBeNull();
  });

  it("normalizes legacy relationship-drift records without using diagnoses", () => {
    const finding = normalizePersistedFinding({
      run_id: "legacy",
      status: "complete",
      observation_type: "relationship_drift",
      observation_status: "open",
      structural_state: "High",
      system_id: "pump_loop",
      variables: ["pump_power_kw", "flow_gpm", "pump_speed_pct"],
      evidence_summary: ["Persistent relationship movement."],
      deformation_started_at: "2026-07-24T00:00:00Z",
      completed_at: "2026-07-25T00:00:00Z",
    });
    expect(finding.title).toBe("Pump response changed");
    expect(finding.description).toMatch(/no longer responding/i);
    expect(finding.corroborationCount).toBe(3);
    expect(finding.title).not.toMatch(/failure|fault|inspect|repair/i);
  });

  it("creates concise diagnosis-free notification payloads", () => {
    const finding = normalizePersistedFinding({
      run_id: "notification",
      meaningful_change: true,
      status: "complete",
      observation_status: "open",
      variables: ["cooling_demand", "power_usage"],
      deformation_started_at: "2026-07-24T02:10:00Z",
      completed_at: "2026-07-25T02:10:00Z",
    });
    const notification = buildFindingNotification(finding);
    expect(notification.title).toBe("Cooling demand and power usage have diverged.");
    expect(notification.body).toMatch(/no longer moving together/i);
    expect(notification.actionLabel).toBe("View evidence");
    expect(JSON.stringify(notification)).not.toMatch(/cause|repair|inspect/i);
  });

  it("filters active, resolved, system, and date without changing stored records", () => {
    const findings = [
      { id: "one", state: "active", system: "Pumping", firstDetectedAt: "2026-07-24T02:00:00Z" },
      { id: "two", state: "resolved", system: "Cooling", firstDetectedAt: "2026-07-25T02:00:00Z" },
    ];
    expect(filterFindings(findings, { state: "active", system: "all", date: "" }).map((item) => item.id)).toEqual(["one"]);
    expect(filterFindings(findings, { state: "all", system: "Cooling", date: "2026-07-25" }).map((item) => item.id)).toEqual(["two"]);
  });

  it("reports persistence from backend timestamps", () => {
    expect(persistenceLabel({ firstDetectedAt: "2026-07-24T00:00:00Z", lastObservedAt: "2026-07-25T00:00:00Z", raw: {} })).toBe("1 day");
  });
});
