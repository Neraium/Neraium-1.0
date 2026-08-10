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
    [{ explicit: "Confirmed", coverage: 0.8, evidenceCount: 3, limitations: ["gap"] }, "Narrowed"],
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
    expect(finding.primaryLimitation).toBe("Missing telemetry limits the conclusion.");
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
    expect(finding.title).toBe("Condenser-side behavior changed");
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

    expect(model.site.name).toBe("Dataset assignment pending");
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

  it("restores persisted canonical conditions without converting them to legacy findings", () => {
    const models = buildEngineeringReasoningModelsFromEvidenceRuns([{
      run_id: "condition-run",
      adaptive_site_key: "rush-tower",
      site_name: "Rush Tower",
      status: "completed",
      observation_status: "open",
      rows_received: 100,
      rows_accepted: 100,
      evidence_summary: ["3 connected relationships changed together."],
      condition: {
        object_type: "condition",
        condition_id: "condition-pump",
        headline: "Pump response weakening in Rush Tower Pumping System",
        confidence: "high",
        affected_signals: ["Pump power", "Flow", "Discharge pressure"],
        localization: { system: "Pumping System", monitored_boundary: "Discharge boundary" },
        trajectory: { state: "Strengthening", persistence: 0.8 },
        corroboration: { corroboration_strength: "moderate", relationship_count: 3 },
        supporting_relationships: [
          { id: "rel-1", columns: ["Pump power", "Flow"], change_type: "weakened" },
          { id: "rel-2", columns: ["Flow", "Discharge pressure"], change_type: "weakened" },
        ],
        next_checks: ["Verify source data."],
      },
    }]);

    expect(models).toHaveLength(1);
    expect(models[0].selectedFinding.objectType).toBe("condition");
    expect(models[0].selectedFinding.title).toBe("Pumping System relationship weakening");
    expect(models[0].selectedFinding.corroboration.relationship_count).toBe(3);
  });

  it("keeps generic finding language out of location and confidence fields", () => {
    const model = buildEngineeringReasoningModel({ result: {
      data_quality: { coverage_percent: 100, warnings: ["811 rows contain missing numeric values."] },
      analysis_explanation: {
        fingerprint: { status: "Established" },
        systems: [{ name: "Observed subsystem behavior changed" }],
        insights: [{
          id: "finding-1",
          title: "Cooling Distribution Performance Degrading",
          system: "Observed subsystem behavior changed",
          variables: ["Condenser approach temperature", "Compressor amps"],
          confidence: "high",
          supporting_evidence: ["Chiller increased 5.5%.", "The relationship moved outside its learned range."],
        }],
      },
    } });

    const finding = model.selectedFinding;
    expect(finding.title).toBe("Condenser-side behavior changed");
    expect(finding.location.label).toBe("Unassigned dataset · Cooling system");
    expect(finding.location.label).not.toContain("Observed subsystem behavior changed");
    expect(finding.tier).toBe("Narrowed");
    expect(finding.confidenceReason).toBe("Missing telemetry limits the conclusion.");
    expect(finding.technicalLimitations).toContain("811 rows contain missing numeric values.");
    expect(finding.supporting).toContain("Compressor current increased 5.5%.");
  });

  it("carries classification context and normalizes plain legacy guidance for the live workspace", () => {
    const model = buildEngineeringReasoningModel({ result: {
      facility_name: "Legacy Site",
      completed_at: "2026-07-25T10:00:00Z",
      data_quality: { coverage_percent: 100 },
      analysis_explanation: {
        fingerprint: { status: "Established" },
        insights: [{
          id: "legacy-guidance",
          title: "Historical relationship observation",
          system: "Flow system",
          variables: ["flow"],
          supporting_evidence: ["Flow response changed."],
          recommended_investigation: "Review the original operator notes.",
        }],
      },
    } });

    const presentation = model.selectedFinding.classificationPresentation;
    expect(presentation.type).toBe("insufficient_evidence");
    expect(presentation.legacy).toBe(true);
    expect(presentation.dataConfidence.rating).toBe("Unavailable");
    expect(presentation.investigationGuidance[0]).toMatchObject({
      rank: 1,
      check: "Review the original operator notes.",
      category: "documentation",
    });
    expect(presentation.timeline.map((item) => item.eventType)).toEqual(["finding_generated"]);
  });

  it("translates raw relationship coefficients into readable primary evidence", () => {
    expect(formatPrimaryEvidence("Relationship changed from 0.094013 to 0.833811.")).toBe("Relationship changed from weak to strong.");
  });

  it("prefers canonical conditions and carries trajectory, corroboration, and localization", () => {
    const supportingRelationships = [
      { id: "rel-1", columns: ["Pump power", "Flow"], change_type: "weakened", baseline_strength: 0.9, current_strength: 0.3 },
      { id: "rel-2", columns: ["Flow", "Discharge pressure"], change_type: "weakened", baseline_strength: 0.84, current_strength: 0.28 },
      { id: "rel-3", columns: ["Discharge pressure", "Pump speed"], change_type: "weakened", baseline_strength: 0.81, current_strength: 0.24 },
    ];
    const model = buildEngineeringReasoningModel({ result: {
      facility_name: "Rush Tower",
      data_quality: { coverage_percent: 100 },
      analysis_result: {
        fingerprint: { status: "Established" },
        systems: [{ name: "Pumping System" }],
        relationships: supportingRelationships,
        conditions: [{
          object_type: "condition",
          condition_id: "condition-pump",
          headline: "Pump response weakening in Rush Tower water system",
          status: "open",
          confidence: "high",
          classification: { type: "unexplained_systemic_change", confidence: "high", reasons: ["Comparable operating evidence supports the condition."] },
          affected_systems: ["Pumping System"],
          affected_boundaries: ["Discharge boundary"],
          affected_signals: ["Pump power", "Flow", "Discharge pressure", "Pump speed"],
          localization: {
            system: "Pumping System",
            monitored_boundary: "Discharge boundary",
            likely_investigation_area: "Discharge boundary",
          },
          trajectory: {
            state: "Strengthening",
            scope: "evidence_support",
            evidence_window_duration: "18 days",
            corroboration_change: "Corroboration increased from 2 to 3 relationships",
            persistence: 0.85,
          },
          corroboration: {
            corroboration_strength: "moderate",
            relationship_count: 3,
          },
          comparable_operation: {
            status: "supported",
            comparable_period_count: 18,
            normal_behavior: "Pressure increased with pump speed.",
            current_behavior: "Pressure response weakened.",
          },
          supporting_relationships: supportingRelationships,
          supporting_evidence: [
            "3 relationship changes align through flow and discharge pressure.",
            "Pump power and flow coupling changed from strong to weak.",
            "Corroboration increased from 2 to 3 relationships.",
          ],
          next_checks: ["Verify source data and inspect the affected pressure boundary."],
          timeline: [{ event_type: "evidence_trend_classified", title: "Evidence trend: Strengthening", start: "2026-07-01T00:00:00Z", end: "2026-07-19T00:00:00Z" }],
        }],
        insights: [{ id: "legacy-finding", title: "Relationship change detected", supporting_evidence: ["Legacy evidence"] }],
      },
    } });

    expect(model.findings).toHaveLength(1);
    expect(model.selectedFinding.objectType).toBe("condition");
    expect(model.selectedFinding.title).toBe("Pumping System relationship weakening");
    expect(model.selectedFinding.trajectory.state).toBe("Strengthening");
    expect(model.selectedFinding.corroboration.relationship_count).toBe(3);
    expect(model.selectedFinding.location.likelyInvestigationArea).toBe("Discharge boundary");
    expect(model.selectedFinding.location.asset).toBe("");
    expect(model.selectedFinding.comparableOperation.comparable_period_count).toBe(18);
  });
});
