import { describe, expect, it } from "vitest";
import {
  buildEngineeringReasoningModel,
  buildEngineeringReasoningModelsFromEvidenceRuns,
  deriveConfidenceTier,
  formatPrimaryEvidence,
} from "../engineeringReasoning";

describe("engineering reasoning model", () => {
  it.each([
    [{ explicit: "Confirmed", coverage: 1, evidenceCount: 3 }, "Confirmed"],
    [{ explicit: "Confirmed", coverage: 0.8, evidenceCount: 3, limitations: ["gap"] }, "Qualified"],
    [{ explicit: "high", coverage: 1, evidenceCount: 3 }, "Qualified"],
    [{ explicit: "Qualified", coverage: 0.7, evidenceCount: 2 }, "Narrowed"],
    [{ explicit: "pending", coverage: 0.8, evidenceCount: 1, processing: true }, "Deferred"],
    [{ explicit: "Qualified", coverage: 0.9, evidenceCount: 3, baselineSufficient: false }, "Deferred"],
    [{ explicit: "Qualified", coverage: 1, evidenceCount: 3, reliable: false }, "Withheld"],
    [{ explicit: "high", coverage: 0.4, evidenceCount: 2 }, "Withheld"],
  ])("strictly gates the five-tier confidence state", (input, expected) => {
    expect(deriveConfidenceTier({ limitations: [], contradictions: [], processing: false, ...input })).toBe(expected);
  });

  it("withholds an unreliable finding and suppresses unsupported recommendations", () => {
    const model = buildEngineeringReasoningModel({ result: {
      facility_name: "North Plant",
      job_id: "run-1",
      reliable: false,
      data_quality: { coverage_percent: 90, warnings: ["Historian X was unavailable."] },
      data_gaps: [{ source: "Historian X", duration: "2 hours", signals: ["flow"] }],
      analysis_explanation: {
        fingerprint: { status: "Established" },
        systems: [{ name: "Hydronic loop" }],
        insights: [{
          id: "finding-1",
          title: "Flow response weakened",
          what_changed: "Flow response weakened under comparable demand.",
          confidence: "Qualified",
          recommended_check: "Inspect Filter-03",
          system: "Hydronic loop",
          variables: ["flow"],
          supporting_evidence: ["Flow response fell during the current window."],
        }],
      },
    } });

    const finding = model.selectedFinding;
    expect(finding.status).toBe("Evidence insufficient");
    expect(finding.tier).toBe("Withheld");
    expect(finding.recommendationAllowed).toBe(false);
    expect(finding.firstPlaceToLook).toBe("");
    expect(finding.primaryLimitation).toMatch(/Historian X/);
  });

  it("uses specific wording, the deepest supported location, and at most three default evidence points", () => {
    const model = buildEngineeringReasoningModel({ result: {
      facility_name: "Golden Nugget",
      data_quality: { coverage_percent: 100 },
      analysis_explanation: {
        fingerprint: { status: "Established" },
        systems: [{ name: "Cooling Plant" }],
        relationships: [{
          id: "rel-1",
          columns: ["Approach temperature", "Compressor current"],
          change_type: "changed",
          baseline_strength: 0.094013,
          current_strength: 0.833811,
        }],
        insights: [{
          id: "finding-1",
          title: "Relationship change detected",
          what_changed: "Condenser performance changed.",
          system: "Cooling Plant",
          subsystem: "Condenser Water",
          asset: "Chiller 03",
          supporting_evidence: [
            "Approach temperature increased 15.3%.",
            "Compressor current increased 5.5%.",
            "The relationship moved outside its learned range.",
            "Relationship changed from 0.094013 to 0.833811.",
          ],
        }],
      },
    } });

    const finding = model.selectedFinding;
    expect(finding.title).toBe("Condenser performance changed");
    expect(finding.location.hierarchy).toEqual(["Golden Nugget", "Cooling Plant", "Condenser Water", "Chiller 03"]);
    expect(finding.visibleSupporting).toHaveLength(3);
    expect(finding.supporting.join(" ")).not.toMatch(/0\.094013|0\.833811/);
    expect(finding.comparisonSummary).toBe("Relationship was weak at baseline and is strong now.");
  });

  it("does not infer an asset from signal names", () => {
    const model = buildEngineeringReasoningModel({ result: {
      facility_name: "One Site",
      data_quality: { coverage_percent: 100 },
      analysis_explanation: {
        fingerprint: { status: "Established" },
        systems: [{ name: "Flow system" }],
        relationships: [{ id: "rel-1", columns: ["Chiller-03", "Flow-01"], change_type: "changed", baseline_strength: 0.8, current_strength: 0.3 }],
        insights: [{ id: "finding-1", title: "Flow response weakened", system: "Flow system", variables: ["Chiller-03"], supporting_evidence: ["Mapped observation"] }],
      },
    } });

    expect(model.sites).toHaveLength(1);
    expect(model.findings).toHaveLength(1);
    expect(model.relationships[0]).toMatchObject({ source: "Chiller-03", target: "Flow-01", state: "changed" });
    expect(model.selectedFinding.location.asset).toBe("");
    expect(model.searchItems.some((item) => item.label === "Chiller-03")).toBe(true);
  });

  it("uses the explicit unassigned dataset state instead of a fake current site", () => {
    const model = buildEngineeringReasoningModel({ result: {
      data_quality: { coverage_percent: 100 },
      analysis_explanation: {
        fingerprint: { status: "Established" },
        insights: [{ title: "Water-quality relationships shifted", supporting_evidence: ["Conductivity increased 8.2%."] }],
      },
    } });

    expect(model.site.name).toBe("Unassigned Analysis");
    expect(model.site.locationLabel).toBe("Unassigned dataset");
    expect(model.selectedFinding.location.hierarchy[0]).toBe("Unassigned dataset");
  });

  it("reports Normal when analysis is sufficient and has no active findings", () => {
    const model = buildEngineeringReasoningModel({ result: {
      facility_name: "Stable Site",
      data_quality: { coverage_percent: 100 },
      analysis_explanation: {
        fingerprint: { status: "Established" },
        systems: [{ name: "Cooling" }],
        insights: [{ id: "baseline-stable", title: "Relationships remain stable" }],
      },
    } });

    expect(model.status).toBe("Normal");
    expect(model.findings).toHaveLength(0);
  });

  it("builds distinct portfolio sites only from persisted site identities", () => {
    const models = buildEngineeringReasoningModelsFromEvidenceRuns([
      { run_id: "a-old", adaptive_site_key: "site-a", site_name: "Site A", status: "completed", created_at: "2026-07-20T00:00:00Z", rows_received: 10, rows_accepted: 10, evidence_summary: ["Earlier observation"], observation_status: "open", baseline_status: "Established" },
      { run_id: "a-new", adaptive_site_key: "site-a", site_name: "Site A", status: "completed", created_at: "2026-07-21T00:00:00Z", rows_received: 10, rows_accepted: 9, evidence_summary: ["Latest observation"], observation_status: "open", baseline_status: "Established" },
      { run_id: "b", adaptive_site_key: "site-b", site_name: "Site B", status: "completed", created_at: "2026-07-21T00:00:00Z", rows_received: 10, rows_accepted: 10, evidence_summary: [], observation_status: "resolved", baseline_status: "Established" },
    ]);

    expect(models).toHaveLength(2);
    expect(models.find((model) => model.site.id === "site-a").site.lastMeaningfulChange).toBe("Latest observation");
    expect(models.find((model) => model.site.id === "site-b").site.activeInvestigations).toBe(0);
  });

  it("translates raw relationship coefficients into readable primary evidence", () => {
    expect(formatPrimaryEvidence("Relationship changed from 0.094013 to 0.833811.")).toBe("Relationship changed from weak to strong.");
  });
});
