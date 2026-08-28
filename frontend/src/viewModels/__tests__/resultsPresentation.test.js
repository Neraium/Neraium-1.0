import { describe, expect, it } from "vitest";

import { buildEngineeringReasoningModel } from "../engineeringReasoning";
import { projectEvidenceDashboardSummary } from "../../components/engineering/evidenceDashboardProjection";
import {
  EVIDENCE_KEYS,
  INVESTIGATION_KEYS,
  RESULT_CARD_KEYS,
  RESULTS_KEYS,
  REVIEW_KEYS,
  SYSTEM_CARD_KEYS,
  SYSTEMS_KEYS,
  projectEvidenceRecord,
  projectFindingReview,
  projectInvestigation,
  projectResults,
  projectSystems,
} from "../resultsPresentation";

const A = "FINDING_RESULTS_CANARY_A";
const B = "FINDING_RESULTS_CANARY_B";

function fixtureResult() {
  const relationship = (suffix, baseline, current) => ({
    id: `RELATIONSHIP_RESULTS_CANARY_${suffix}`,
    source: `RAW_SIGNAL_RESULTS_CANARY_${suffix}`,
    target: `RAW_TARGET_RESULTS_CANARY_${suffix}`,
    source_display_name: `Source ${suffix}`,
    target_display_name: `Target ${suffix}`,
    metric: "pearson_correlation",
    baseline_value: baseline,
    current_value: current,
    baseline_sample_size: suffix === "A" ? 997 : 211,
    current_sample_size: suffix === "A" ? 443 : 199,
    source_time_ranges: [{
      baseline_start: "2026-07-01T00:00:00+00:00",
      baseline_end: "2026-07-31T23:59:59+00:00",
      current_start: "2026-08-20T00:00:00+00:00",
      current_end: "2026-08-25T05:23:56.206210+00:00",
    }],
    evidence_refs: [`LINEAGE_RESULTS_CANARY_${suffix}`],
    persistence: { status: "persistent" },
  });
  const condition = (suffix, packageId) => ({
    id: suffix === "A" ? A : B,
    condition_id: `CONDITION_RESULTS_CANARY_${suffix}`,
    object_type: "condition",
    title: `System behavior ${suffix} changed`,
    what_changed: `The learned system response ${suffix} changed during comparable operation. Additional sentence should be bounded away.`,
    why_it_matters: `The change ${suffix} persisted across the comparison and deserves engineering review.`,
    confidence_tier: "Confirmed",
    reliable: true,
    system: `Cooling system ${suffix}`,
    asset: `Asset ${suffix}`,
    variables: [`RAW_SIGNAL_RESULTS_CANARY_${suffix}`, `RAW_TARGET_RESULTS_CANARY_${suffix}`],
    signals: [{ raw_id: `RAW_SIGNAL_RESULTS_CANARY_${suffix}`, canonical_id: `CANONICAL_SIGNAL_CANARY_${suffix}` }],
    supporting_relationships: [relationship(suffix, suffix === "A" ? 0.918273 : 0.7123, suffix === "A" ? 0.314159 : 0.6123)],
    supporting_evidence: [`System relationship ${suffix} changed outside the learned range.`, "CORROBORATION_RESULTS_CANARY"],
    evidence_items: [{ description: `Persistent relationship evidence ${suffix}` }, { description: `Comparable operation evidence ${suffix}` }],
    limitations: [`Material limitation ${suffix}: missing efficiency history limits attribution.`],
    data_limitations: [`TECHNICAL_LIMITATION_RESULTS_CANARY_${suffix}`],
    contradicting_evidence: [`CONTRADICTION_RESULTS_CANARY_${suffix}`],
    recommended_investigation: ["GUIDANCE_RESULTS_CANARY", "Inspect the control sequence record.", "Compare the current operating mode.", "A fourth check must be removed."],
    finding_confidence_v1: {
      change_detection: { level: "High" },
      evidence_quality: { level: "Moderate" },
      interpretation: { attribution_status: "Not established" },
      persistence: { status: "Persistent" },
      operating_context: { status: "comparable" },
      evidence_sufficiency: { status: "Supported", reasons: ["SUFFICIENCY_RESULTS_CANARY"] },
    },
    corroboration: { corroboration_strength: "Moderate", relationship_count: 2 },
    operating_mode: { baseline_mode: "occupied cooling", recent_mode: "occupied cooling", match: "strong" },
    persistence: { status: "persistent", window: "four comparison windows" },
    sensor_health: { signals: [{ signal: `RAW_SIGNAL_RESULTS_CANARY_${suffix}`, status: "usable" }] },
    source_time_ranges: [{ current_end: "2026-08-25T05:23:56.206210+00:00" }],
    first_detected_at: "2026-08-25T05:23:56.206210+00:00",
    classification: { type: "unexplained_systemic_change", internal_panel: "CLASSIFICATION_RESULTS_CANARY" },
    provenance: { record: `LINEAGE_RESULTS_CANARY_${suffix}` },
    finding_status_history: [{ state: "open", at: "2026-08-25T05:23:56.206210+00:00" }],
    operator_feedback_history: [{ category: "AUDIT_RESULTS_CANARY" }],
    ...(packageId ? { evidence_package_id: packageId } : {}),
  });
  return {
    comparison_analysis_id: "RUN_RESULTS_CANARY",
    run_id: "RUN_RESULTS_CANARY",
    upload_id: "UPLOAD_RESULTS_CANARY",
    dataset_id: "DATASET_RESULTS_CANARY",
    baseline_id: "BASELINE_RESULTS_CANARY",
    baseline_sufficient: true,
    site_name: "Canary plant",
    sii_completed: true,
    completed_at: "2026-08-25T05:23:56.206210+00:00",
    engine_name: "ENGINE_RESULTS_CANARY",
    engine_version: "9.7.3",
    schema_version: "SCHEMA_RESULTS_CANARY",
    result_hash: "RESULT_HASH_RESULTS_CANARY",
    traceability: { lineage: "TRACEABILITY_RESULTS_CANARY" },
    processing_trace: [{ event: "PROCESSING_TRACE_RESULTS_CANARY" }],
    analysis_explanation: {
      systems: [{ id: "SYSTEM_A", name: "Cooling system A" }, { id: "SYSTEM_B", name: "Cooling system B" }],
      conditions: [condition("A", "PACKAGE_RESULTS_CANARY_A"), condition("B")],
      sii_evidence: {
        relationship_changes: [{ id: "RUN_RELATIONSHIP_RESULTS_CANARY" }],
        operating_context: { status: "RUN_CONTEXT_RESULTS_CANARY" },
        persistence: { status: "RUN_PERSISTENCE_RESULTS_CANARY" },
        data_quality: { rating: "RUN_QUALITY_RESULTS_CANARY" },
        phase_4: { behavioral_evolution: { summary: "RUN_EVOLUTION_RESULTS_CANARY" } },
        provenance: { id: "RUN_PROVENANCE_RESULTS_CANARY" },
      },
    },
    sii_result: {
      covariance_analysis: { summary: "MULTIVARIATE_RESULTS_CANARY", determinant_delta: 0 },
      temporal_analysis: {
        summary: "TEMPORAL_RESULTS_CANARY",
        lagged_relationships: [{ lag: 17, id: "LAG_RESULTS_CANARY" }],
        mutual_information_drift: [{ value: 0.271828, id: "MI_RESULTS_CANARY" }],
      },
      persistence_analysis: { status: "PERSISTENCE_RESULTS_CANARY" },
      operating_modes: { mode: "MODE_RESULTS_CANARY" },
      data_conditions: { usable: false, missing: 0 },
      physics_reasoning: { status: "PHYSICS_RESULTS_CANARY" },
    },
    evidence_package: {
      id: "PACKAGE_RESULTS_CANARY_A",
      analysis_id: "RUN_RESULTS_CANARY",
      immutable: true,
      primary_relationship: { source_model_edge_id: "RELATIONSHIP_RESULTS_CANARY_A" },
      internal: "PACKAGE_INTERNAL_RESULTS_CANARY",
    },
  };
}

function modelFrom(result = fixtureResult()) {
  const model = buildEngineeringReasoningModel({ result });
  model.status = "Change detected";
  model.findings = model.findings.map((finding) => ({ ...finding, status: "Change detected", tier: "Narrowed" }));
  model.selectedFinding = model.findings[0] ?? null;
  return model;
}

function keys(value) {
  return Object.keys(value).sort();
}

describe("results presentation contracts", () => {
  it("projects an exact allowlisted Results contract without technical canaries", () => {
    const sourceModel = modelFrom();
    const projection = projectResults(sourceModel, {
      [A]: { state: "investigating", priority: "high", assignment: { label: "Mechanical" } },
    });
    expect(keys(projection)).toEqual([...RESULTS_KEYS].sort());
    expect(projection.variant).toBe("ready");
    expect(projection.counts).toEqual({ findingsForReview: 2, systemsRepresented: 2 });
    expect(projection.cards).toHaveLength(2);
    expect(keys(projection.cards[0])).toEqual([...RESULT_CARD_KEYS].sort());
    expect(projection.cards[0]).toMatchObject({ priority: "high", reviewState: "Investigating", assignment: "Mechanical" });
    expect(projection.cards[1]).toMatchObject({ reviewState: "Not reviewed", assignment: "Unassigned" });
    expect(projection.eyebrow).toBe("Operations Brief");
    const rendered = JSON.stringify(projection);
    for (const forbidden of ["RAW_SIGNAL_RESULTS_CANARY", "CANONICAL_SIGNAL_CANARY", "pearson_correlation", "0.918273", "997", "2026-08-25T05:23:56", "LINEAGE_RESULTS_CANARY", "ENGINE_RESULTS_CANARY", "PACKAGE_RESULTS_CANARY", "GUIDANCE_RESULTS_CANARY", "CORROBORATION_RESULTS_CANARY", "CLASSIFICATION_RESULTS_CANARY"]) {
      expect(rendered).not.toContain(forbidden);
    }
  });

  it("keeps Review decision-oriented and the seven dimensions independent", () => {
    const projection = projectFindingReview(modelFrom(), A, { state: "investigating" });
    expect(keys(projection)).toEqual([...REVIEW_KEYS].sort());
    expect(projection.variant).toBe("ready");
    expect(Object.keys(projection.assessment)).toEqual([
      "changeConfidence", "evidenceQuality", "causeAttribution", "persistence", "operatingContext", "corroboration", "evidenceSufficiency",
    ]);
    expect(projection.assessment.changeConfidence.value).toBe("High");
    expect(projection.assessment.causeAttribution.value).toBe("Not established");
    expect(projection.whyAttention.length).toBeGreaterThanOrEqual(1);
    expect(projection.whyAttention.length).toBeLessThanOrEqual(3);
    expect(projection.checks.length).toBeLessThanOrEqual(3);
    const rendered = JSON.stringify(projection);
    for (const forbidden of ["RAW_SIGNAL_RESULTS_CANARY", "pearson_correlation", "0.918273", "997", "LINEAGE_RESULTS_CANARY", "ENGINE_RESULTS_CANARY", "PACKAGE_RESULTS_CANARY", "CLASSIFICATION_RESULTS_CANARY"]) expect(rendered).not.toContain(forbidden);
  });

  it("materially deepens finding-owned evidence in Investigation with explicit run scope", () => {
    const projection = projectInvestigation(modelFrom(), A);
    expect(keys(projection)).toEqual([...INVESTIGATION_KEYS].sort());
    expect(projection.primaryComparison).toMatchObject({
      id: "RELATIONSHIP_RESULTS_CANARY_A",
      baseline: 0.918273,
      current: 0.314159,
      baselineSamples: 997,
      currentSamples: 443,
      metricChannel: "pearson_correlation",
    });
    expect(JSON.stringify(projection.sourceSignals)).toContain("RAW_SIGNAL_RESULTS_CANARY_A");
    const multivariate = projection.systemEvidence.find((channel) => channel.key === "multivariate");
    expect(multivariate).toMatchObject({ state: { state: "available", reason: "" }, scope: "run", scopeLabel: "Analysis-run evidence; not finding-specific", sourcePath: "model.result.sii_result.covariance_analysis" });
    expect(projection.systemEvidence.find((channel) => channel.key === "lag").summary).toBe("");
    const rendered = JSON.stringify(projection);
    expect(rendered).not.toContain("PACKAGE_INTERNAL_RESULTS_CANARY");
    expect(rendered).not.toContain("ENGINE_RESULTS_CANARY");
    expect(rendered).not.toContain("AUDIT_RESULTS_CANARY");
  });

  it("retains exact provenance and all available channels only at Evidence depth", () => {
    const projection = projectEvidenceRecord(modelFrom(), A, { state: "investigating", note: "AUDIT_REVIEW_RESULTS_CANARY" });
    expect(keys(projection)).toEqual([...EVIDENCE_KEYS].sort());
    expect(projection.identity).toMatchObject({ findingId: A, runId: "RUN_RESULTS_CANARY", uploadId: "UPLOAD_RESULTS_CANARY", datasetId: "DATASET_RESULTS_CANARY" });
    expect(projection.exactRelationships[0]).toMatchObject({ id: "RELATIONSHIP_RESULTS_CANARY_A", baseline: 0.918273, current: 0.314159, baselineSampleCount: 997 });
    expect(projection.package).toMatchObject({
      scope: "finding",
      packageId: "PACKAGE_RESULTS_CANARY_A",
      sourcePath: "finding.evidence_package_id",
      relationshipLink: { state: "matched", relationshipId: "RELATIONSHIP_RESULTS_CANARY_A" },
    });
    const rendered = JSON.stringify(projection);
    for (const required of ["RAW_SIGNAL_RESULTS_CANARY_A", "CANONICAL_SIGNAL_CANARY_A", "pearson_correlation", "0.918273", "997", "2026-08-25T05:23:56.206210+00:00", "LINEAGE_RESULTS_CANARY_A", "ENGINE_RESULTS_CANARY", "PACKAGE_INTERNAL_RESULTS_CANARY", "MI_RESULTS_CANARY", "LAG_RESULTS_CANARY", "CLASSIFICATION_RESULTS_CANARY", "SUFFICIENCY_RESULTS_CANARY", "AUDIT_RESULTS_CANARY", "AUDIT_REVIEW_RESULTS_CANARY", "CORROBORATION_RESULTS_CANARY", "Persistent relationship evidence A"]) expect(rendered).toContain(required);
    expect(projection.channels.find((channel) => channel.key === "data_quality").payload).toEqual({ usable: false, missing: 0 });
  });

  it("builds the primary evidence summary only from authoritative finding fields", () => {
    const result = fixtureResult();
    const raw = result.analysis_explanation.conditions[0];
    raw.title = "RAW AUTHORITATIVE FINDING TITLE";
    raw.system = "RAW AUTHORITATIVE SYSTEM";
    raw.source_time_ranges[0].current_start = "2026-08-20T00:00:00+00:00";
    const model = modelFrom(result);
    expect(model.findings[0].title).not.toBe(raw.title);

    const projection = projectEvidenceRecord(model, A);
    expect(projectEvidenceDashboardSummary(projection)).toMatchObject({
      title: "RAW AUTHORITATIVE FINDING TITLE",
      system: "RAW AUTHORITATIVE SYSTEM",
      status: "Change detected",
      evidenceWindow: {
        label: "Aug 20 – Aug 25, 2026",
        start: "2026-08-20T00:00:00+00:00",
        end: "2026-08-25T05:23:56.206210+00:00",
      },
      metrics: {
        magnitude: { value: -0.604114, signed: true, description: "relationship shift" },
        persistence: { value: "Persistent" },
        operatingContext: { value: "Comparable" },
        confidence: { value: "High" },
      },
      cause: { established: false, label: "No — investigation required" },
    });
  });

  it("uses a finding-owned relationship window when the finding-level window is absent", () => {
    const result = fixtureResult();
    delete result.analysis_explanation.conditions[0].source_time_ranges;
    const projection = projectEvidenceRecord(modelFrom(result), A);
    expect(projectEvidenceDashboardSummary(projection).evidenceWindow).toEqual({
      label: "Aug 20 – Aug 25, 2026",
      start: "2026-08-20T00:00:00+00:00",
      end: "2026-08-25T05:23:56.206210+00:00",
    });
  });

  it("preserves authoritative relationship order, signs, missing values, and the three-row limit", () => {
    const result = fixtureResult();
    const raw = result.analysis_explanation.conditions[0];
    raw.supporting_relationships = [
      { ...raw.supporting_relationships[0], id: "ORDERED_1", source_display_name: "Flow", target_display_name: "Pressure", baseline_value: 0.2, current_value: 0.7 },
      { ...raw.supporting_relationships[0], id: "ORDERED_2", source_display_name: "Power", target_display_name: "Flow", baseline_value: 0.8, current_value: 0.3 },
      { ...raw.supporting_relationships[0], id: "ORDERED_3", source_display_name: "Valve", target_display_name: "Demand", baseline_value: null, current_value: null },
      { ...raw.supporting_relationships[0], id: "ORDERED_4", source_display_name: "Hidden", target_display_name: "Fourth", baseline_value: 0.1, current_value: 0.9 },
    ];
    const summary = projectEvidenceDashboardSummary(projectEvidenceRecord(modelFrom(result), A));
    expect(summary.relationships).toHaveLength(3);
    expect(summary.relationships.map((relationship) => relationship.id)).toEqual(["ORDERED_1", "ORDERED_2", "ORDERED_3"]);
    expect(summary.relationships.map((relationship) => relationship.label)).toEqual([
      "Flow ↔ Pressure", "Power ↔ Flow", "Valve ↔ Demand",
    ]);
    expect(summary.relationships[0].magnitude).toBeCloseTo(0.5);
    expect(summary.relationships[0].signed).toBe(true);
    expect(summary.relationships[1].magnitude).toBeCloseTo(-0.5);
    expect(summary.relationships[1].signed).toBe(true);
    expect(summary.relationships[2]).toMatchObject({ magnitude: null });
  });

  it("fails closed for unsupported summary metrics and only confirms an explicit cause", () => {
    const unsupported = fixtureResult();
    const raw = unsupported.analysis_explanation.conditions[0];
    raw.supporting_relationships = [];
    delete raw.persistence;
    delete raw.finding_confidence_v1.persistence;
    delete raw.finding_confidence_v1.operating_context;
    delete raw.finding_confidence_v1.change_detection;
    delete raw.confidence_tier;
    delete raw.operating_mode;
    delete raw.comparable_operation;
    raw.reliable = false;
    const summary = projectEvidenceDashboardSummary(projectEvidenceRecord(modelFrom(unsupported), A));
    expect(summary.metrics.magnitude).toMatchObject({ value: null, label: "Not established" });
    expect(summary.metrics.persistence.value).toBe("Not established");
    expect(summary.metrics.operatingContext.value).toBe("Not established");
    expect(summary.metrics.confidence.value).not.toMatch(/strong|confirmed/i);
    expect(summary.relationships).toEqual([]);
    expect(summary.cause).toEqual({ established: false, label: "No — investigation required" });

    const confirmed = fixtureResult();
    confirmed.analysis_explanation.conditions[0].cause_established = true;
    expect(projectEvidenceDashboardSummary(projectEvidenceRecord(modelFrom(confirmed), A)).cause).toEqual({ established: true, label: "Yes — confirmed in evidence" });
  });

  it("prevents cross-finding relationship, lineage, and package attribution", () => {
    const model = modelFrom();
    const a = projectEvidenceRecord(model, A);
    const b = projectEvidenceRecord(model, B);
    expect(a.exactRelationships.map((item) => item.id)).toEqual(["RELATIONSHIP_RESULTS_CANARY_A"]);
    expect(b.exactRelationships.map((item) => item.id)).toEqual(["RELATIONSHIP_RESULTS_CANARY_B"]);
    expect(JSON.stringify(b.exactRelationships)).not.toContain("RELATIONSHIP_RESULTS_CANARY_A");
    expect(JSON.stringify(b.lineage)).not.toContain("LINEAGE_RESULTS_CANARY_A");
    expect(b.package).toMatchObject({
      scope: "run",
      scopeLabel: "Related package for this analysis run; not finding provenance",
      sourcePath: "model.result.evidence_package",
      relationshipLink: { state: "different" },
    });
    expect(b.identity).not.toHaveProperty("packageId");
    expect(JSON.stringify(b.lineage)).not.toContain("PACKAGE_RESULTS_CANARY_A");
  });

  it("preserves canonical projection truncation and exact source/reference qualification", () => {
    const result = fixtureResult();
    Object.assign(result, {
      result_id: "77777777-7777-4777-8777-777777777777",
      analysis_window_id: "88888888-8888-4888-8888-888888888888",
      source_run_id: "44444444-4444-4444-8444-444444444444",
      connection_id: "11111111-1111-4111-8111-111111111111",
      facility_id: "facility-a",
      system_id: "SYSTEM_A",
      asset_id: "chiller-03",
      payload_digest: "a".repeat(64),
      canonical_result: {
        identity: {
          result_id: "77777777-7777-4777-8777-777777777777",
          analysis_window_id: "88888888-8888-4888-8888-888888888888",
          source_ingestion_run_id: "44444444-4444-4444-8444-444444444444",
          connection_id: "11111111-1111-4111-8111-111111111111",
          facility_id: "facility-a",
          system_id: "SYSTEM_A",
          asset_id: "chiller-03",
          payload_digest: "a".repeat(64),
          observation_count: 2,
          observation_lineage_digest: "d".repeat(64),
        },
        reference_metadata: { model_id: "model-17", baseline_snapshot_id: "snapshot-9" },
      },
      projection: {
        contract_version: "telemetry-canonical-result-product.v1",
        canonical_result_id: "77777777-7777-4777-8777-777777777777",
        canonical_payload_digest: "a".repeat(64),
        shared: { source_path: "analysis_result", truncated: false, omitted_values: 0 },
        technical_channels: {
          covariance_analysis: { source_path: "sii_result.covariance_analysis", original_items: 140, selected_items: 32, original_bytes: 300000, selected_bytes: 100000, truncated: true, transported: true },
        },
        evidence_audit: { source_path: "analysis_result.conditions|analysis_result.insights", truncated: false, omitted_values: 0 },
      },
    });
    const model = modelFrom(result);
    const investigation = projectInvestigation(model, A);
    const evidence = projectEvidenceRecord(model, A);

    expect(investigation.projectionQualification).toMatchObject({
      contractVersion: "telemetry-canonical-result-product.v1",
      canonicalResultId: result.result_id,
      truncated: true,
      referenceMetadata: { model_id: "model-17", baseline_snapshot_id: "snapshot-9" },
      truncatedSources: ["sii_result.covariance_analysis"],
    });
    expect(investigation.systemEvidence.find((channel) => channel.key === "multivariate")).toMatchObject({
      sourcePath: "sii_result.covariance_analysis",
      qualification: { truncated: true, originalItems: 140, selectedItems: 32, canonicalResultId: result.result_id },
    });
    expect(evidence.channels.find((channel) => channel.key === "multivariate")).toMatchObject({
      sourcePath: "sii_result.covariance_analysis",
      qualification: { truncated: true, canonicalPayloadDigest: "a".repeat(64) },
    });
    expect(evidence.identity).toMatchObject({
      resultId: result.result_id,
      connectionId: result.connection_id,
      sourceRunId: result.source_run_id,
      systemId: result.system_id,
      assetId: result.asset_id,
      observationCount: 2,
      observationLineageDigest: "d".repeat(64),
    });
  });

  it("does not treat an index-generated relationship display ID as source ownership", () => {
    const result = fixtureResult();
    result.analysis_explanation.conditions[1].supporting_relationships = [];
    result.analysis_explanation.conditions[1].relationship_id = "relationship-0";
    result.analysis_explanation.relationships = [{ source: "A", target: "B", baseline: 0.9, current: 0.1 }];
    const b = projectEvidenceRecord(modelFrom(result), B);
    expect(b.exactRelationships).toEqual([]);
    expect(JSON.stringify(b.channels.find((channel) => channel.key === "finding_relationships"))).not.toContain("0.9");
  });

  it("fails closed for mismatched package identity and missing package run scope", () => {
    const mismatch = fixtureResult();
    mismatch.analysis_explanation.conditions[1].evidence_package_id = "DIFFERENT_PACKAGE";
    expect(projectEvidenceRecord(modelFrom(mismatch), B).package).toMatchObject({ scope: "unavailable", packageId: null });
    const missingRun = fixtureResult();
    delete missingRun.evidence_package.analysis_id;
    expect(projectEvidenceRecord(modelFrom(missingRun), B).package).toMatchObject({ scope: "unavailable", packageId: null });
  });

  it("returns safe unavailable variants for malformed inputs and unknown identities", () => {
    const malformed = { hasAnalysis: true, findings: "not-an-array", result: Object.create({ secret: true }) };
    expect(() => projectResults(malformed)).not.toThrow();
    for (const projection of [
      projectFindingReview(malformed, "secret-unknown"),
      projectInvestigation(modelFrom(), "secret-unknown"),
      projectEvidenceRecord(modelFrom(), "secret-unknown"),
    ]) {
      expect(projection.variant).toBe("unavailable");
      expect(JSON.stringify(projection)).not.toContain("secret-unknown");
    }
    const hostile = fixtureResult();
    hostile.sii_result.covariance_analysis = Object.assign(Object.create({ inherited: "secret" }), { valid: Number.NaN });
    const evidence = projectEvidenceRecord(modelFrom(hostile), A);
    expect(evidence.channels.find((channel) => channel.key === "multivariate").payload).toBeNull();
  });

  it("uses exact calm stable and source-backed insufficient result states", () => {
    const stableModel = modelFrom();
    stableModel.status = "Normal";
    stableModel.findings = [];
    const stable = projectResults(stableModel);
    expect(stable).toMatchObject({ variant: "ready", outcome: "stable", headline: "No supported material behavioral change.", cards: [], counts: { findingsForReview: 0, systemsRepresented: 0 } });
    const insufficientModel = modelFrom();
    insufficientModel.status = "Evidence insufficient";
    insufficientModel.findings = [{ ...insufficientModel.findings[0], status: "Evidence insufficient", tier: "Withheld" }];
    const insufficient = projectResults(insufficientModel);
    expect(insufficient).toMatchObject({ variant: "insufficient", headline: "Insufficient evidence", counts: { findingsForReview: 0, systemsRepresented: 1 } });
    expect(insufficient.improvement).toBe("More complete operating history would improve the assessment.");
    expect(insufficient.auditAction).toEqual({
      label: "Open evidence record",
      route: `/evidence/${A}`,
      findingKey: A,
    });
    const insufficientEvidence = projectEvidenceRecord(insufficientModel, A);
    expect(insufficientEvidence).toMatchObject({ variant: "insufficient", identity: { findingKey: A } });
    expect(projectEvidenceDashboardSummary(insufficientEvidence)).toMatchObject({ insufficient: { title: "Insufficient evidence" } });
    expect(projectEvidenceDashboardSummary(insufficientEvidence).relationships).toHaveLength(1);
  });

  it("separates supported findings from insufficient evidence and resolved workflow", () => {
    const mixed = modelFrom();
    mixed.findings[1] = { ...mixed.findings[1], status: "Evidence insufficient", tier: "Withheld" };
    const projectedMixed = projectResults(mixed);
    expect(projectedMixed).toMatchObject({
      variant: "ready",
      outcome: "analysis_complete",
      counts: { findingsForReview: 1, systemsRepresented: 1 },
    });
    expect(projectedMixed.cards.map((card) => card.findingKey)).toEqual([A]);

    const resolved = projectResults(modelFrom(), {
      [A]: { state: "resolved" },
      [B]: { status: "dismissed" },
    });
    expect(resolved).toMatchObject({
      variant: "ready",
      outcome: "analysis_complete",
      headline: "Analysis complete",
      explanation: "No findings currently deserve review from this completed analysis.",
      counts: { findingsForReview: 0, systemsRepresented: 0 },
      cards: [],
    });
    expect(resolved.headline).not.toContain("No supported material behavioral change");
  });

  it("fails unavailable for malformed or contradictory result semantics", () => {
    expect(projectResults({ ...modelFrom(), findings: { 0: modelFrom().findings[0] } }).variant).toBe("unavailable");
    expect(projectResults({ ...modelFrom(), findings: [Object.create({ id: "INHERITED_FINDING" })] }).variant).toBe("unavailable");
    expect(projectResults({ ...modelFrom(), status: "Normal" }).variant).toBe("unavailable");
    expect(projectResults({ ...modelFrom(), status: "Evidence insufficient" }).variant).toBe("unavailable");

    const analyzedWithoutReviewable = modelFrom();
    analyzedWithoutReviewable.findings = analyzedWithoutReviewable.findings.map((finding) => ({ ...finding, status: "Evidence insufficient", tier: "Deferred" }));
    const complete = projectResults(analyzedWithoutReviewable);
    expect(complete).toMatchObject({ variant: "ready", outcome: "analysis_complete", headline: "Analysis complete", cards: [] });
    expect(complete.explanation).toContain("No findings currently deserve review");
  });

  it("projects system overviews without handing subsystem or evidence DTOs to components", () => {
    const projection = projectSystems(modelFrom(), { [A]: { state: "investigating" } });
    expect(keys(projection)).toEqual([...SYSTEMS_KEYS].sort());
    expect(projection.variant).toBe("ready");
    expect(projection.header.summary).toBe("2 modeled systems");
    expect(projection.systems).toHaveLength(2);
    expect(keys(projection.systems[0])).toEqual([...SYSTEM_CARD_KEYS].sort());
    expect(projection.systems[0].results.cards.map((card) => card.findingKey)).toEqual([A]);
    const rendered = JSON.stringify(projection);
    for (const forbidden of ["RAW_SIGNAL_RESULTS_CANARY", "pearson_correlation", "0.918273", "997", "LINEAGE_RESULTS_CANARY", "ENGINE_RESULTS_CANARY", "PACKAGE_RESULTS_CANARY"]) {
      expect(rendered).not.toContain(forbidden);
    }
  });

  it("does not read inherited review or evidence-channel properties", () => {
    const inheritedRecords = Object.create({
      [A]: { state: "resolved", assignment: { label: "INHERITED_ASSIGNMENT_TEXT" } },
    });
    const results = projectResults(modelFrom(), inheritedRecords);
    expect(results.cards).toHaveLength(2);
    expect(JSON.stringify(results)).not.toContain("INHERITED_ASSIGNMENT_TEXT");

    const hostile = fixtureResult();
    hostile.sii_result.covariance_analysis = Object.assign(Object.create({ summary: "INHERITED_CHANNEL_TEXT" }), { own: "ignored" });
    const model = modelFrom(hostile);
    const investigation = projectInvestigation(model, A);
    const evidence = projectEvidenceRecord(model, A);
    expect(investigation.systemEvidence.find((channel) => channel.key === "multivariate")).toMatchObject({
      state: { state: "unavailable" },
      summary: "",
    });
    expect(evidence.channels.find((channel) => channel.key === "multivariate")).toMatchObject({
      state: { state: "unavailable" },
      payload: null,
    });
    expect(JSON.stringify([investigation, evidence])).not.toContain("INHERITED_CHANNEL_TEXT");
  });

  it("keeps all presentation projections isolated from later source and projection mutation", () => {
    const model = modelFrom();
    const results = projectResults(model);
    const systems = projectSystems(model);
    const investigation = projectInvestigation(model, A);
    const evidence = projectEvidenceRecord(model, A);
    const snapshots = [results, systems, investigation, evidence].map((projection) => JSON.stringify(projection));

    expect(investigation.relationships).not.toBe(model.findings[0].relationships);
    expect(evidence.exactRelationships).not.toBe(model.findings[0].relationships);
    expect(evidence.package.immutableDetails).not.toBe(model.result.evidence_package);
    model.findings[0].title = "SOURCE_MUTATION_CANARY";
    model.findings[0].relationships[0].baseline = -77;
    model.result.evidence_package.internal = "SOURCE_PACKAGE_MUTATION_CANARY";
    expect([results, systems, investigation, evidence].map((projection) => JSON.stringify(projection))).toEqual(snapshots);

    results.cards[0].title = "PROJECTION_MUTATION_CANARY";
    systems.systems[0].results.cards[0].behavior = "PROJECTION_SYSTEM_MUTATION_CANARY";
    investigation.relationships[0].baseline = -88;
    evidence.exactRelationships[0].baseline = -99;
    evidence.package.immutableDetails.internal = "PROJECTION_PACKAGE_MUTATION_CANARY";
    expect(model.findings[0].title).toBe("SOURCE_MUTATION_CANARY");
    expect(model.findings[0].relationships[0].baseline).toBe(-77);
    expect(model.result.evidence_package.internal).toBe("SOURCE_PACKAGE_MUTATION_CANARY");
  });

  it("has live and history projection parity and never consults another model", () => {
    const live = modelFrom();
    const historical = modelFrom(structuredClone(fixtureResult()));
    expect(projectResults(live, {}, { sourceMode: "live" })).toEqual(projectResults(historical, {}, { sourceMode: "historical" }));
    expect(projectEvidenceRecord(live, A)).toEqual(projectEvidenceRecord(historical, A));
    delete historical.result.sii_result.temporal_analysis;
    const compacted = projectEvidenceRecord(historical, A);
    expect(compacted.channels.find((channel) => channel.key === "lag").state.state).toBe("unavailable");
    expect(compacted.channels.find((channel) => channel.key === "mutual_information").state.state).toBe("unavailable");
  });
});
