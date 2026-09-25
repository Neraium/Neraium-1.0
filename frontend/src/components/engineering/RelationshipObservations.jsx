import React from "react";
import "../../styles/evidence-dashboard.css";

const display = (value) => typeof value === "boolean" ? (value ? "Yes" : "No")
  : typeof value === "number" && Number.isFinite(value) ? String(value)
    : typeof value === "string" && value ? value : "Not recorded";

function Fact({ label, value }) {
  return <div><dt>{label}</dt><dd>{display(value)}</dd></div>;
}

const comparisonBasis = {
  global_relationship_model: "Global relationship model",
  global_relationship_model_failure_fallback: "Global relationship model",
  mode_conditioned_relationships: "Like-mode relationships",
};
const comparisonStatus = { complete: "Complete", limited: "Limited", failed: "Unavailable" };
const comparisonReason = {
  no_explicit_operating_mode_features: "Operating-mode features were not available.",
  insufficient_recent_mode_rows: "Too few recent samples in this operating mode.",
  ambiguous_recent_operating_mode: "The recent operating mode was ambiguous.",
  insufficient_like_mode_historical_rows: "Too few historical samples in this operating mode.",
};
const safeLabel = (labels, value) => typeof value === "string" && Object.hasOwn(labels, value) ? labels[value] : "Not available";

function ComparisonQualification({ qualification }) {
  if (!qualification || typeof qualification !== "object") return null;
  const mode = qualification.mode_conditioned_baseline ?? {};
  return <>
    {Object.hasOwn(qualification, "edge_basis") ? <Fact label="Comparison basis" value={safeLabel(comparisonBasis, qualification.edge_basis)} /> : null}
    {qualification.edge_basis === "global_relationship_model_failure_fallback" ? <Fact label="Comparison basis qualification" value="Dynamic relationship comparison was unavailable for this evaluation." /> : null}
    {Object.hasOwn(mode, "status") ? <Fact label="Like-mode comparison status" value={safeLabel(comparisonStatus, mode.status)} /> : null}
    {typeof mode.used_global_fallback === "boolean" ? <Fact label="Global fallback used" value={mode.used_global_fallback} /> : null}
    {mode.used_global_fallback === true || mode.fallback_reason != null ? <Fact label="Comparison limitation" value={safeLabel(comparisonReason, mode.fallback_reason)} /> : null}
  </>;
}

export default function RelationshipObservations({ evidence }) {
  if (evidence?.version !== "relationship-observations.v1" || evidence.authority !== "observation_only" || !Array.isArray(evidence.observations)) return null;
  const coverage = evidence.coverage ?? {};
  return <details className="evidence-record-technical relationship-observations">
    <summary>Show relationship evidence</summary>
    <p>Observed evidence is separate from a promoted finding. Inspection does not change the assessment, evidence sufficiency, or measurable-consequence status.</p>
    <dl className="classification-detail-grid">
      <Fact label="Relationships evaluated" value={coverage.evaluated} />
      <Fact label="Eligible relationships" value={coverage.eligible} />
      <Fact label="Relationships with temporal support" value={coverage.temporally_supported} />
      <Fact label="Promoted changed edges" value={coverage.promoted_changed_edges} />
    </dl>
    <p>Counts cover retained graph edges; upstream pair coverage is not reported here.</p>
    <p>Showing {display(coverage.displayed)} relationships in recorded engine order, with {display(coverage.omitted)} omitted from this bounded disclosure. This order is not the primary or strongest-relationship ranking. Graph edge promotion does not establish a persistent finding.</p>
    {evidence.observations.slice(0, 12).map((item, index) => <details key={index}>
      <summary>{Array.isArray(item.columns) ? item.columns.filter((column) => typeof column === "string").join(" ↔ ") : "Relationship"} — Observed</summary>
      <dl className="classification-detail-grid">
        <Fact label="Recorded change" value={item.change_type} />
        <Fact label="Single-window change" value={item.single_window_change_type} />
        <Fact label="Baseline correlation (unitless)" value={item.baseline_correlation} />
        <Fact label="Current correlation (unitless)" value={item.current_correlation} />
        <Fact label="Recorded signed correlation change (unitless)" value={item.signed_correlation_delta} />
        <Fact label="Eligible under existing rules" value={item.eligible} />
        <Fact label="Promoted changed edge" value={item.promoted_changed_edge} />
        <Fact label="Temporal support status" value={item.temporal_persistence_status} />
        <Fact label="Temporal support established" value={item.temporal_persistence_supported} />
        <Fact label="Temporal observations" value={item.temporal_persistence_observations} />
        <Fact label="Supporting observations" value={item.temporal_persistence_supporting_observations} />
        <Fact label="Recorded direction (-1 / 0 / 1)" value={item.temporal_persistence_direction} />
        <Fact label="Direction agreement" value={item.temporal_persistence_direction_agreement} />
        <Fact label="Persistent relationship change" value={item.persistent_relationship_change} />
        <Fact label="Recurrence status" value={item.recurrence?.status} />
        <Fact label="Recurrence supported" value={item.recurrence?.supported} />
        <Fact label="Recurrence episodes" value={item.recurrence?.episode_count} />
        <Fact label="Opposite-direction veto" value={item.recurrence?.opposite_direction_veto} />
        <Fact label="General operating-mode match" value={item.operating_context?.match} />
        <Fact label="Operating context status" value={item.operating_context?.status} />
        <ComparisonQualification qualification={evidence.comparison_qualification} />
        <Fact label="Eligible for operator primary selection" value={item.relationship_context?.operator_primary_eligible} />
        <Fact label="Baseline samples" value={item.baseline_sample_count} />
        <Fact label="Current samples" value={item.current_sample_count} />
        <Fact label="Sample sufficiency factor" value={item.sample_sufficiency_factor} />
        <Fact label="Edge confidence" value={item.edge_confidence} />
        <Fact label="Data quality factor" value={item.data_quality_factor} />
      </dl>
      <p>Missing or unsupported dimensions remain limitations. Recorded support does not establish comparability or satisfy other promotion requirements. A specific gate reason is not inferred here.</p>
      <details><summary>Reference and source evidence</summary>
        <dl className="classification-detail-grid">
          <Fact label="Relationship ID" value={item.id ?? item.relationship_id} />
          <Fact label="Source path in this result" value={item.source_path} />
          <Fact label="Reference dataset" value={item.reference_dataset_id} />
          <Fact label="Baseline start" value={item.time_window?.baseline_start} />
          <Fact label="Baseline end" value={item.time_window?.baseline_end} />
          <Fact label="Current start" value={item.time_window?.current_start} />
          <Fact label="Current end" value={item.time_window?.current_end} />
        </dl>
        {Array.isArray(item.supporting_windows) ? item.supporting_windows.slice(0, 8).map((window, windowIndex) => <dl className="classification-detail-grid" key={windowIndex}>
          <Fact label="Supported observation time" value={window.observed_at} />
          <Fact label="Source dataset" value={window.source_dataset_id} />
          <Fact label="Recorded signed correlation change" value={window.signed_correlation_delta} />
          {Array.isArray(window.source_rows) ? window.source_rows.slice(0, 4).map((anchor, anchorIndex) => <React.Fragment key={anchorIndex}>
            <Fact label="Source window" value={anchor.window} /><Fact label="Source row" value={anchor.source_row} /><Fact label="Source timestamp" value={anchor.timestamp} />
          </React.Fragment>) : null}
        </dl>) : null}
      </details>
    </details>)}
  </details>;
}
