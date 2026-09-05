/* @vitest-environment jsdom */
import React from "react";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EvidenceRecordWorkspace, FindingReviewWorkspace, InvestigationWorkspace } from "./FindingCaseWorkspaces";

afterEach(cleanup);

const header = { systemContext: "Cooling plant", title: "Cooling relationship changed", reviewState: "New" };

function reviewProjection() {
  return {
    contractVersion: "results-presentation.v1",
    depth: "review",
    variant: "ready",
    identity: { findingKey: "finding-a" },
    header,
    whatChanged: "Return temperature and chiller power no longer follow the learned relationship.",
    whyAttention: ["The change affects two connected operating signals."],
    assessment: {
      changeConfidence: { value: "High", state: "supported" },
      evidenceQuality: { value: "Medium", state: "supported" },
      causeAttribution: { value: "Not established", state: "unknown" },
      persistence: { value: "Observing", state: "limited" },
      operatingContext: { value: "Weak match", state: "limited" },
      corroboration: { value: "Limited · 1 relationship", state: "limited" },
      evidenceSufficiency: { value: "Supported for review", state: "supported" },
    },
    materialLimitation: "Operating context differs from baseline.",
    checks: [{ label: "Verify the relevant source signals." }],
    primaryAction: { label: "Open investigation", route: "/investigations/finding-a" },
  };
}

function investigationProjection() {
  const relationship = {
    id: "rel-a",
    source: { display: "Return temperature", sourceId: "RAW_SIGNAL_A" },
    target: { display: "Chiller power", sourceId: "RAW_SIGNAL_B" },
    metricChannel: "Correlation strength",
    baseline: 0.88,
    current: 0.2,
    signedChange: -0.68,
    magnitude: 0.68,
    direction: "decreased",
    baselineSamples: 120,
    currentSamples: 48,
    windows: [{ baselineStart: "2026-08-01T00:00:00Z", baselineEnd: "2026-08-10T00:00:00Z", currentStart: "2026-08-20T00:00:00Z", currentEnd: "2026-08-25T00:00:00Z" }],
    persistence: "observing",
    support: "limited",
  };
  return {
    contractVersion: "results-presentation.v1", depth: "investigation", variant: "ready", identity: { findingKey: "finding-a" }, header,
    primaryComparison: relationship, relationships: [relationship], relationshipMap: null,
    systemEvidence: [{ key: "multivariate", label: "Multivariate system evidence", state: { state: "available", reason: "" }, scope: "run", scopeLabel: "Analysis-run evidence; not finding-specific", sourcePath: "model.result.sii_result.covariance_analysis", summary: "Cross-signal structure changed.", metrics: [] }],
    persistence: { state: { state: "available", reason: "" }, summary: "Observing", supportTrend: "Stable", windowDescription: "Five comparable windows" },
    operatingContext: { state: { state: "available", reason: "" }, baselineMode: "Mid load", currentMode: "High load", comparability: "Weak", reasons: ["Load differed from baseline."] },
    dataQuality: { state: { state: "available", reason: "" }, summary: "Usable with limits.", limitations: ["Historian coverage was reduced."], signalHealth: [{ signal: "Pressure", status: "Suspect" }] },
    timeline: [{ label: "Finding generated", detail: "Current comparison" }],
    sourceSignals: [{ display: "Return temperature", sourceId: "RAW_SIGNAL_A" }, { display: "Chiller power", sourceId: "RAW_SIGNAL_B" }],
    lineageSummary: { source: "comparison.csv", baselineWindow: "Learned baseline", currentWindow: "Current comparison", evidenceRefs: ["EVIDENCE_A"] },
    primaryAction: { label: "Open evidence record", route: "/evidence/finding-a" },
  };
}

function evidenceProjection(scope = "run") {
  return {
    contractVersion: "results-presentation.v1", depth: "evidence", variant: "ready",
    identity: { findingKey: "finding-a", findingId: "FINDING_A", workflowFindingId: null, conditionId: null, runId: "RUN_A", uploadId: "UPLOAD_A", datasetId: "DATASET_A", baselineId: "BASELINE_A", systemId: "SYSTEM_A", assetId: null },
    header,
    dashboardIdentity: { title: "RAW AUTHORITATIVE EVIDENCE TITLE", system: "RAW AUTHORITATIVE SYSTEM", status: "Change detected", causeEstablished: false },
    timestamps: { generatedAt: "2026-08-25T05:23:56.206210+00:00", firstDetectedAt: null, sourceRanges: [] },
    signals: [{ display: "Return temperature", rawId: "RAW_SIGNAL_A", canonicalId: "CANONICAL_SIGNAL_A" }],
    exactRelationships: [{ id: "RELATIONSHIP_A", source: "Return temperature", target: "Chiller power", baseline: 0.918273, current: 0.314159, signedChange: -0.604114 }],
    supportingEvidence: { statements: ["SUPPORTING_EVIDENCE_A"], items: [{ id: "EVIDENCE_ITEM_A" }] },
    channels: [{ key: "multivariate", label: "Multivariate evidence", state: { state: "available", reason: "" }, scope: "run", scopeLabel: "Analysis-run evidence; not finding-specific", sourcePath: "model.result.sii_result.covariance_analysis", payload: { usable: false, missing: 0 } }],
    classifications: { classification: { type: "CLASSIFICATION_A" }, confidenceContract: { version: "CONFIDENCE_A" }, alternatives: [] },
    sufficiency: { status: "SUFFICIENCY_A", reasons: [] },
    limitations: { material: ["No cause is established."], technical: [], contradictions: [] },
    lineage: { sourceRows: [{ id: "LINEAGE_A" }], evidenceWindows: [], evidenceRefs: ["EVIDENCE_A"], traceability: null, findingProvenance: null },
    engine: { name: "ENGINE_A", version: "4.2", schemaVersion: null, buildCommit: null, configurationHash: null, inputHash: null, resultHash: null },
    package: { scope, scopeLabel: scope === "finding" ? "Package explicitly linked to this finding" : "Related package for this analysis run; not finding provenance", sourcePath: "model.result.evidence_package", packageId: "PACKAGE_A", immutableDetails: { id: "PACKAGE_A" }, relationshipLink: { state: "matched" } },
    audit: { caseState: "open", caseHistory: [], outcome: null, review: null, trace: [] },
    actions: { exportRunId: "RUN_A", exportScopeLabel: "Analysis-run export; not finding-specific", traceRoute: null },
  };
}

function canonicalEvidenceProjection() {
  return {
    ...evidenceProjection("unavailable"),
    identity: {
      findingKey: "finding-a",
      findingId: "FINDING_A",
      resultId: "77777777-7777-4777-8777-777777777777",
      analysisWindowId: "88888888-8888-4888-8888-888888888888",
      sourceRunId: "44444444-4444-4444-8444-444444444444",
      connectionId: "11111111-1111-4111-8111-111111111111",
      systemId: "cooling-loop",
      assetId: "chiller-03",
      payloadDigest: "a".repeat(64),
      observationCount: 2,
      observationLineageDigest: "d".repeat(64),
    },
    channels: [{
      key: "temporal",
      label: "Temporal evidence",
      state: { state: "available", reason: "" },
      scope: "run",
      scopeLabel: "Analysis-run evidence; not finding-specific",
      sourcePath: "sii_result.temporal_analysis",
      qualification: { sourcePath: "sii_result.temporal_analysis", truncated: true, transported: true },
      payload: { status: "changed" },
    }],
    projectionQualification: {
      contractVersion: "telemetry-canonical-result-product.v1",
      canonicalResultId: "77777777-7777-4777-8777-777777777777",
      canonicalPayloadDigest: "a".repeat(64),
      referenceMetadata: { model_id: "model-17" },
      truncated: true,
      truncatedSources: ["sii_result.temporal_analysis"],
    },
  };
}

function response(payload, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

describe("progressive results hierarchy", () => {
  it("keeps Finding Review decision-oriented and preserves independent confidence dimensions", () => {
    render(React.createElement(FindingReviewWorkspace, { projection: reviewProjection() }));
    for (const heading of ["What changed", "Why this deserves attention", "Evidence assessment", "Important limitation", "Where to investigate next"]) expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
    const assessment = screen.getByRole("heading", { name: "Evidence assessment" }).closest("section");
    for (const label of ["Change confidence", "Evidence quality", "Persistence", "Operating context", "Corroboration", "Evidence sufficiency"]) expect(within(assessment).getByText(label)).toBeTruthy();
    expect(within(assessment).queryByText("Cause / attribution")).toBeNull();
    expect(screen.getByText("Verify the relevant source signals.")).toBeTruthy();
    expect(document.body.textContent).not.toContain("RAW_SIGNAL_A");
    expect(screen.queryByText("Audit history")).toBeNull();
  });

  it("materially deepens Investigation while keeping run evidence visibly scoped", () => {
    render(React.createElement(InvestigationWorkspace, { projection: investigationProjection() }));
    expect(screen.getByText("Correlation strength decreased by 0.68 from the learned baseline.")).toBeTruthy();
    expect(screen.getByText("120 baseline · 48 current")).toBeTruthy();
    expect(screen.getAllByText("RAW_SIGNAL_A").length).toBeGreaterThan(0);
    expect(screen.getByText("Analysis-run evidence; not finding-specific")).toBeTruthy();
    expect(screen.getByText("model.result.sii_result.covariance_analysis")).toBeTruthy();
    expect(screen.queryByText("PACKAGE_A")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Audit history" })).toBeNull();
  });

  it("keeps complete technical depth and exact false/zero values in Evidence Record", () => {
    const apiFetch = vi.fn();
    render(React.createElement(EvidenceRecordWorkspace, { projection: evidenceProjection("run"), apiFetch }));
    for (const value of ["FINDING_A", "RAW_SIGNAL_A", "CANONICAL_SIGNAL_A", "RELATIONSHIP_A", "0.918273", "0.314159", "SUPPORTING_EVIDENCE_A", "EVIDENCE_ITEM_A", "LINEAGE_A", "ENGINE_A", "PACKAGE_A", '"usable": false', '"missing": 0']) expect(document.body.textContent).toContain(value);
    expect(screen.getByRole("heading", { name: "Related package for this analysis run" })).toBeTruthy();
    expect(screen.getAllByText(/not finding provenance/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { level: 1, name: "RAW AUTHORITATIVE EVIDENCE TITLE" })).toBeTruthy();
    expect(screen.getByText("RAW AUTHORITATIVE SYSTEM")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Strongest Relationship Changes" })).toBeTruthy();
    expect(screen.queryByText("Cause established?")).toBeNull();
    expect(screen.getByText("Technical evidence and audit trail")).toBeTruthy();
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("loads related-package context only for an explicitly linked finding package", async () => {
    const apiFetch = vi.fn(async () => ({ ok: true, json: async () => ({ matches: [] }) }));
    render(React.createElement(EvidenceRecordWorkspace, { projection: evidenceProjection("finding"), apiFetch }));
    expect(screen.getByRole("heading", { name: "Package explicitly linked to this finding" })).toBeTruthy();
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
    expect(apiFetch.mock.calls[0][0]).toContain("PACKAGE_A");
  });

  it("loads every exact scoped lineage page before rendering canonical provenance", async () => {
    const resultId = "77777777-7777-4777-8777-777777777777";
    const windowId = "88888888-8888-4888-8888-888888888888";
    const digest = "d".repeat(64);
    const records = ["obs-1", "obs-2"].map((observation_id) => ({ observation_id, connection_id: "11111111-1111-4111-8111-111111111111", system_id: "cooling-loop", asset_id: "chiller-03" }));
    const apiFetch = vi.fn(async (path) => {
      if (path.includes("cursor=next-page")) return response({ result_id: resultId, analysis_window_id: windowId, observation_count: 2, observation_lineage_digest: digest, lineage_verified: true, records: [records[1]], next_cursor: null });
      return response({ result_id: resultId, analysis_window_id: windowId, observation_count: 2, observation_lineage_digest: digest, lineage_verified: true, records: [records[0]], next_cursor: "next-page" });
    });

    render(React.createElement(EvidenceRecordWorkspace, { projection: canonicalEvidenceProjection(), apiFetch }));

    await waitFor(() => expect(screen.getByText(/2 observations verified/)).toBeTruthy());
    expect(document.body.textContent).toContain("obs-1");
    expect(document.body.textContent).toContain("obs-2");
    expect(document.body.textContent).toContain("model-17");
    expect(screen.getAllByText(/bounded projection/i).length).toBeGreaterThan(0);
    expect(apiFetch).toHaveBeenCalledTimes(2);
    expect(apiFetch.mock.calls[0][0]).toBe(`/api/data-connections/11111111-1111-4111-8111-111111111111/runs/44444444-4444-4444-8444-444444444444/systems/cooling-loop/analysis-results/${resultId}/lineage?asset_id=chiller-03&limit=2`);
    expect(apiFetch.mock.calls[1][0]).toBe(`/api/data-connections/11111111-1111-4111-8111-111111111111/runs/44444444-4444-4444-8444-444444444444/systems/cooling-loop/analysis-results/${resultId}/lineage?asset_id=chiller-03&limit=2&cursor=next-page`);
  });

  it("fails lineage display opaquely and discards partial pages when identity changes", async () => {
    const projection = canonicalEvidenceProjection();
    const apiFetch = vi.fn(async (path) => path.includes("cursor=next-page")
      ? response({ result_id: "99999999-9999-4999-8999-999999999999", analysis_window_id: projection.identity.analysisWindowId, observation_count: 2, observation_lineage_digest: projection.identity.observationLineageDigest, lineage_verified: true, records: [{ observation_id: "must-not-render" }], next_cursor: null })
      : response({ result_id: projection.identity.resultId, analysis_window_id: projection.identity.analysisWindowId, observation_count: 2, observation_lineage_digest: projection.identity.observationLineageDigest, lineage_verified: true, records: [{ observation_id: "partial-must-not-render", connection_id: projection.identity.connectionId, system_id: projection.identity.systemId, asset_id: projection.identity.assetId }], next_cursor: "next-page" }));

    render(React.createElement(EvidenceRecordWorkspace, { projection, apiFetch }));

    await waitFor(() => expect(screen.getByText("Exact canonical observation lineage is unavailable for this scoped result.")).toBeTruthy());
    expect(document.body.textContent).not.toContain("partial-must-not-render");
    expect(document.body.textContent).not.toContain("must-not-render");
    expect(document.body.textContent).not.toContain("canonical_lineage_identity_mismatch");
  });
});
