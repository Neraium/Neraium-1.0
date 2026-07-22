import { describe, expect, it } from "vitest";
import { buildEngineeringReasoningModel, buildEngineeringReasoningModelsFromEvidenceRuns, deriveConfidenceTier } from "../engineeringReasoning";

describe("engineering reasoning model", () => {
  it.each([
    [{ explicit: "Confirmed", coverage: 1, evidenceCount: 3 }, "Confirmed"],
    [{ explicit: "Confirmed", coverage: 0.8, evidenceCount: 3, limitations: ["gap"] }, "Qualified"],
    [{ explicit: "high", coverage: 1, evidenceCount: 3 }, "Qualified"],
    [{ explicit: "moderate", coverage: 0.7, evidenceCount: 2 }, "Narrowed"],
    [{ explicit: "pending", coverage: 0.8, evidenceCount: 1, processing: true }, "Deferred"],
    [{ explicit: "high", coverage: 0.4, evidenceCount: 2 }, "Withheld"],
  ])("derives a bounded five-tier state", (input, expected) => {
    expect(deriveConfidenceTier({ limitations: [], contradictions: [], processing: false, ...input })).toBe(expected);
  });

  it("separates observation, interpretation, limitations, and suppresses unsupported recommendations", () => {
    const model = buildEngineeringReasoningModel({ result: {
      facility_name: "North Plant",
      job_id: "run-1",
      data_quality: { coverage_percent: 40, warnings: ["Historian X was unavailable."] },
      data_gaps: [{ source: "Historian X", duration: "2 hours", signals: ["flow"] }],
      analysis_explanation: {
        systems: [{ name: "Hydronic loop" }],
        insights: [{ id: "finding-1", title: "Flow relationship changed", what_changed: "Flow response weakened under comparable demand.", why_it_matters: "The response may indicate a subsystem behavior change.", confidence: "high", recommended_check: "Inspect Filter-03", system: "Hydronic loop", variables: ["flow"], supporting_evidence: ["Flow response fell during the current window."] }],
      },
    } });
    const finding = model.selectedFinding;
    expect(finding.observedChange).toMatch(/Flow response weakened/);
    expect(finding.whyItMatters).toMatch(/subsystem behavior/);
    expect(finding.tier).toBe("Withheld");
    expect(finding.recommendationAllowed).toBe(false);
    expect(finding.firstPlaceToLook).toBe("");
    expect(finding.limitations.join(" ")).toMatch(/Historian X/);
    expect(model.gaps[0].signals).toContain("flow");
  });

  it("builds distinct portfolio sites only from persisted evidence identities", () => {
    const models = buildEngineeringReasoningModelsFromEvidenceRuns([
      { run_id: "a-old", adaptive_site_key: "site-a", room: "Site A", status: "completed", created_at: "2026-07-20T00:00:00Z", rows_received: 10, rows_accepted: 10, evidence_summary: ["Earlier observation"], observation_status: "open" },
      { run_id: "a-new", adaptive_site_key: "site-a", room: "Site A", status: "completed", created_at: "2026-07-21T00:00:00Z", rows_received: 10, rows_accepted: 9, evidence_summary: ["Latest observation"], observation_status: "open" },
      { run_id: "b", adaptive_site_key: "site-b", room: "Site B", status: "completed", created_at: "2026-07-21T00:00:00Z", rows_received: 10, rows_accepted: 10, evidence_summary: [], observation_status: "resolved" },
    ]);
    expect(models).toHaveLength(2);
    expect(models.find((model) => model.site.id === "site-a").site.lastMeaningfulChange).toBe("Latest observation");
    expect(models.find((model) => model.site.id === "site-b").site.activeInvestigations).toBe(0);
  });

  it("maps relationship evidence without inventing additional sites or findings", () => {
    const model = buildEngineeringReasoningModel({ result: {
      facility_name: "One Site", data_quality: { coverage_percent: 100 },
      analysis_explanation: {
        systems: [{ name: "Flow system" }],
        relationships: [{ id: "rel-1", columns: ["Chiller-03", "Flow-01"], change_type: "weakened", baseline_strength: 0.8, current_strength: 0.3 }],
        insights: [{ id: "finding-1", title: "Mapped change", system: "Flow system", variables: ["Chiller-03"], supporting_evidence: ["Mapped observation"], recommended_check: "Review Chiller-03 trend" }],
      },
    } });
    expect(model.sites).toHaveLength(1);
    expect(model.findings).toHaveLength(1);
    expect(model.relationships[0]).toMatchObject({ source: "Chiller-03", target: "Flow-01", state: "weakening" });
    expect(model.searchItems.some((item) => item.label === "Chiller-03")).toBe(true);
  });
});
