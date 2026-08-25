import React from "react";
import { normalizeFindingPresentation } from "../../viewModels/operatorFinding";
import { formatLocalTimestamp, formatLocalTimestampRange, resolveDisplayTimeZone, timestampTechnicalTitle } from "../../utils/dateTime";
import { reviewStateLabel } from "../../viewModels/findingReviewState";
import FindingClassificationSummary from "../operational/FindingClassificationSummary";
import EvidenceLineage from "./EvidenceLineage";
import EvidencePackageExport from "./EvidencePackageExport";
import FindingReviewActions from "./FindingReviewActions";
import FindingWorkflowPanel from "./FindingWorkflow";
import RelatedEvidencePackages from "./RelatedEvidencePackages";
import RelationshipGraph from "./RelationshipGraph";

function runIdentity(model, finding) {
  return finding?.runId ?? model?.result?.run_id ?? model?.result?.job_id ?? model?.result?.upload_id ?? null;
}

function packageIdentity(model) {
  return model?.result?.evidence_package?.id ?? null;
}

function sentence(value) {
  const clean = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!clean) return "";
  const first = clean.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() ?? clean;
  return /[.!?]$/.test(first) ? first : `${first}.`;
}

function uniqueText(values) {
  return [...new Set(values.map((value) => String(value ?? "").trim()).filter(Boolean))];
}

function displayLabel(value, fallback = "Unavailable") {
  const text = String(value ?? "").trim();
  return text ? text.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()) : fallback;
}

function evidenceNumber(value, { signed = false } = {}) {
  if (value === null || value === undefined || value === "") return "Not supplied";
  const number = Number(value);
  if (!Number.isFinite(number)) return "Not supplied";
  const precision = Math.abs(number) > 0 && Math.abs(number) < 0.01 ? 3 : 2;
  const formatted = number.toFixed(precision).replace(/\.?0+$/, "");
  return signed && number > 0 ? `+${formatted}` : formatted;
}

function metricLabel(value) {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (normalized === "pearson_correlation") return "Correlation strength";
  if (normalized === "spearman_correlation") return "Rank correlation";
  return displayLabel(value, "Relationship strength");
}

function simpleValue(value, fallback = "Unavailable") {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (["string", "number"].includes(typeof value)) return displayLabel(value, fallback);
  return fallback;
}

function SimpleList({ items, empty = "No items were recorded." }) {
  const values = (Array.isArray(items) ? items : []).filter((item) => ["string", "number"].includes(typeof item));
  return values.length ? <ul>{values.map((item, index) => <li key={`${item}-${index}`}>{String(item)}</li>)}</ul> : <p className="case-unavailable">{empty}</p>;
}

export function SiiEvidenceRecord({ evidence }) {
  if (!evidence || typeof evidence !== "object") return null;
  const relationships = Array.isArray(evidence.relationship_changes) ? evidence.relationship_changes : [];
  const context = evidence.operating_context ?? {};
  const persistence = evidence.persistence ?? {};
  const uncertainty = evidence.uncertainty ?? {};
  const quality = evidence.data_quality ?? {};
  const sensorHealth = evidence.sensor_health ?? {};
  const configuredPrior = Array.isArray(evidence.configured_prior_observations) ? evidence.configured_prior_observations : [];
  const phase4 = evidence.phase_4 ?? {};
  const evolution = phase4.behavioral_evolution ?? {};
  const propagation = phase4.propagation ?? {};
  const propagationSupported = phase4.available === true && !/unavailable|insufficient|not[_ -]?supported/i.test(String(propagation.status ?? phase4.status ?? ""));
  const provenance = evidence.provenance ?? {};
  const provenanceRows = [
    ["Schema", provenance.schema_version], ["Analysis run", provenance.analysis_run_id], ["Upload", provenance.upload_id], ["Dataset", provenance.dataset_id],
    ["Baseline", provenance.baseline_id], ["Baseline version", provenance.baseline_version], ["Engine", provenance.engine_name ?? evidence.engine?.name],
    ["Engine version", provenance.engine_version ?? evidence.engine?.version], ["Build", provenance.build_commit], ["Configuration hash", provenance.configuration_hash],
    ["Input hash", provenance.input_hash], ["Result hash", provenance.result_hash],
  ].filter(([, value]) => value !== null && value !== undefined && value !== "");
  return (
    <details className="case-classification-detail sii-evidence-record" data-testid="sii-evidence-record">
      <summary>Authoritative SII evidence record</summary>
      <p className="technical-record-note">Separate canonical SII comparison. It does not replace the active finding comparator or classification.</p>
      <div className="sii-evidence-sections">
        <section><h3>Source</h3><dl className="classification-detail-grid"><div><dt>Status</dt><dd>{simpleValue(evidence.status)}</dd></div><div><dt>Source</dt><dd>{simpleValue(evidence.source)}</dd></div><div><dt>Engine</dt><dd>{simpleValue(evidence.engine?.name)}</dd></div><div><dt>Version</dt><dd>{simpleValue(evidence.engine?.version)}</dd></div></dl></section>
        <section><h3>Relationship evidence</h3>{relationships.length ? <ul className="sii-relationship-list">{relationships.map((item, index) => <li key={item.id ?? item.relationship_id ?? index}><strong>{[item.source ?? item.source_signal, item.target ?? item.target_signal].filter(Boolean).join(" / ") || item.relationship || `Relationship ${index + 1}`}</strong><dl><div><dt>Change</dt><dd>{simpleValue(item.change_type ?? item.status)}</dd></div><div><dt>Baseline</dt><dd>{simpleValue(item.baseline_correlation ?? item.baseline_strength)}</dd></div><div><dt>Current</dt><dd>{simpleValue(item.current_correlation ?? item.recent_correlation ?? item.current_strength)}</dd></div><div><dt>Persistence</dt><dd>{simpleValue(item.persistence)}</dd></div></dl></li>)}</ul> : <p className="case-unavailable">No canonical relationship changes were available.</p>}</section>
        <section><h3>Operating context</h3><dl className="classification-detail-grid"><div><dt>Status</dt><dd>{simpleValue(context.status)}</dd></div><div><dt>Baseline mode</dt><dd>{simpleValue(context.baseline_mode)}</dd></div><div><dt>Recent mode</dt><dd>{simpleValue(context.recent_mode)}</dd></div><div><dt>Match</dt><dd>{simpleValue(context.match)}</dd></div><div><dt>Confidence</dt><dd>{simpleValue(context.confidence)}</dd></div></dl><SimpleList items={context.limitations} empty="No operating-context limitations were recorded." /></section>
        <section><h3>Persistence</h3><dl className="classification-detail-grid"><div><dt>Status</dt><dd>{simpleValue(persistence.status)}</dd></div><div><dt>Method</dt><dd>{simpleValue(persistence.method)}</dd></div><div><dt>Covariance gates</dt><dd>{simpleValue(persistence.covariance_gates?.status ?? persistence.covariance_gates)}</dd></div><div><dt>Adaptive evidence</dt><dd>{simpleValue(persistence.adaptive_persistence?.status)}</dd></div></dl></section>
        <section><h3>Uncertainty and data quality</h3><dl className="classification-detail-grid"><div><dt>Uncertainty</dt><dd>{simpleValue(uncertainty.status)}</dd></div><div><dt>Data confidence</dt><dd>{simpleValue(uncertainty.data_confidence)}</dd></div><div><dt>Quality status</dt><dd>{simpleValue(quality.status)}</dd></div><div><dt>Readiness</dt><dd>{simpleValue(quality.readiness ?? quality.analysis_gate_state)}</dd></div><div><dt>Reliability</dt><dd>{simpleValue(quality.reliability_rating ?? quality.reliability_score)}</dd></div></dl><SimpleList items={[...(Array.isArray(uncertainty.limitations) ? uncertainty.limitations : []), ...(Array.isArray(quality.warnings) ? quality.warnings : []), ...(Array.isArray(quality.limitations) ? quality.limitations : [])]} empty="No uncertainty or quality limitations were recorded." /></section>
        <section><h3>Sensor health</h3><dl className="classification-detail-grid"><div><dt>Status</dt><dd>{simpleValue(sensorHealth.status)}</dd></div><div><dt>Reason</dt><dd>{simpleValue(sensorHealth.reason)}</dd></div></dl>{Array.isArray(sensorHealth.signals) && sensorHealth.signals.length ? <ul>{sensorHealth.signals.map((signal, index) => <li key={signal.signal ?? signal.signal_id ?? index}><strong>{simpleValue(signal.signal ?? signal.signal_id, `Signal ${index + 1}`)}</strong> · {simpleValue(signal.health ?? signal.status)}</li>)}</ul> : <p className="case-unavailable">No sensor-health records were available.</p>}</section>
        <section><h3>Configured-prior evidence · Phase 3</h3>{configuredPrior.length ? <ul>{configuredPrior.map((item, index) => <li key={item.observation_id ?? index}><strong>{simpleValue(item.behavioral_status, `Observation ${index + 1}`)}</strong> · Human review {simpleValue(item.human_review_required)}</li>)}</ul> : <p className="case-unavailable">Phase 3 configured-prior evidence is unavailable.</p>}</section>
        <section><h3>Behavioral evolution · Phase 4</h3><dl className="classification-detail-grid"><div><dt>Status</dt><dd>{simpleValue(phase4.status)}</dd></div><div><dt>Available</dt><dd>{simpleValue(phase4.available)}</dd></div><div><dt>Evolution</dt><dd>{simpleValue(evolution.status)}</dd></div><div><dt>Classification</dt><dd>{simpleValue(evolution.evidence_classification)}</dd></div></dl><SimpleList items={[...(Array.isArray(phase4.limitations) ? phase4.limitations : []), ...(Array.isArray(evolution.limitations) ? evolution.limitations : [])]} empty="No Phase 4 limitations were recorded." />{propagationSupported ? <details><summary>Propagation evidence</summary><dl className="classification-detail-grid"><div><dt>Status</dt><dd>{simpleValue(propagation.status)}</dd></div><div><dt>Classification</dt><dd>{simpleValue(propagation.evidence_classification)}</dd></div><div><dt>Confidence</dt><dd>{simpleValue(propagation.propagation_confidence)}</dd></div></dl>{Array.isArray(propagation.candidate_paths) && propagation.candidate_paths.length ? <ul>{propagation.candidate_paths.map((path, index) => <li key={path.path_id ?? index}><strong>{Array.isArray(path.nodes) && path.nodes.length ? path.nodes.join(" → ") : simpleValue(path.path_id, `Candidate path ${index + 1}`)}</strong> · Compatibility {simpleValue(path.compatibility)}</li>)}</ul> : <p className="case-unavailable">No supported propagation paths were recorded.</p>}<SimpleList items={propagation.limitations} empty="No propagation limitations were recorded." /></details> : null}</section>
        <section><h3>Provenance</h3>{provenanceRows.length ? <dl className="classification-detail-grid">{provenanceRows.map(([term, value]) => <div key={term}><dt>{term}</dt><dd>{String(value)}</dd></div>)}</dl> : <p className="case-unavailable">Provenance was not supplied.</p>}</section>
      </div>
    </details>
  );
}

function comparisonWindowLabel(value, timeZone) {
  const source = String(value ?? "").trim();
  if (!source) return "Unavailable";
  const [start, end] = source.split(/\s+to\s+/i);
  if (start && end && !Number.isNaN(new Date(start).getTime()) && !Number.isNaN(new Date(end).getTime())) return formatLocalTimestampRange(start, end, timeZone);
  return source;
}

function comparisonWindowTitle(value, timeZone) {
  const source = String(value ?? "").trim();
  if (!source) return undefined;
  const timestamp = source.split(/\s+to\s+/i)[0];
  return Number.isNaN(new Date(timestamp).getTime()) ? undefined : timestampTechnicalTitle(source, timeZone);
}

function RelationshipComparison({ finding, timeZone = "" }) {
  const comparison = finding.comparison ?? {};
  const hasValues = [comparison.baselineValue, comparison.currentValue, comparison.signedChange].some((value) => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value)));
  if (!hasValues) return <p className="case-unavailable">A numeric baseline comparison was not recorded.</p>;
  const direction = comparison.direction === "decreased" ? "decreased" : comparison.direction === "increased" ? "increased" : "changed";
  const magnitude = evidenceNumber(comparison.absoluteChange);
  return (
    <div className="evidence-comparison">
      <p className="evidence-comparison__summary">{metricLabel(comparison.metric)} {direction}{magnitude === "Not supplied" ? "" : ` by ${magnitude}`} from the learned baseline.</p>
      <dl>
        <div><dt>Baseline</dt><dd>{evidenceNumber(comparison.baselineValue)}<small title={comparisonWindowTitle(comparison.baseline, timeZone)}>{comparisonWindowLabel(comparison.baseline, timeZone)}</small></dd></div>
        <div><dt>Current</dt><dd>{evidenceNumber(comparison.currentValue)}<small title={comparisonWindowTitle(comparison.current, timeZone)}>{comparisonWindowLabel(comparison.current, timeZone)}</small></dd></div>
        <div><dt>Change</dt><dd>{evidenceNumber(comparison.signedChange, { signed: true })}<small>{displayLabel(comparison.direction, "Comparison recorded")}</small></dd></div>
      </dl>
    </div>
  );
}

function relationshipWindow(window, timeZone) {
  if (!window || typeof window !== "object") return "";
  const start = window.current_start ?? window.recent_start ?? window.start ?? window.timestamp_start;
  const end = window.current_end ?? window.recent_end ?? window.end ?? window.timestamp_end;
  return start || end ? formatLocalTimestampRange(start, end, timeZone) : String(window.current_label ?? window.label ?? "").trim();
}

function relationshipNodes(relationships) {
  const labels = uniqueText(relationships.flatMap((item) => [item.source, item.target]));
  return labels.map((label, index) => ({
    id: label,
    label,
    kind: "signal",
    x: 18 + ((index * 37) % 66),
    y: 18 + ((index * 29) % 48),
  }));
}

function RelationshipEvidenceList({ finding, timeZone }) {
  const relationships = finding.relationships ?? [];
  if (!relationships.length) return <p className="case-unavailable">No relationship-level comparison was recorded.</p>;
  const relationshipEvidence = finding.relationshipEvidence ?? {};
  return (
    <ol className="investigation-relationship-list">
      {relationships.map((item, index) => {
        const baselineSamples = item.baselineSampleCount ?? (index === 0 ? relationshipEvidence.baseline_sample_size : null);
        const currentSamples = item.currentSampleCount ?? (index === 0 ? relationshipEvidence.recent_sample_size ?? relationshipEvidence.current_sample_size : null);
        const window = relationshipWindow(item.windows?.[0], timeZone);
        const magnitude = evidenceNumber(item.absoluteChange);
        const rawSignals = uniqueText([item.rawSource, item.rawTarget]).filter((signal) => ![item.source, item.target].includes(signal));
        return (
          <li key={item.id || item.label}>
            <header><span>Relationship {index + 1}</span><strong>{item.source} ↔ {item.target}</strong>{rawSignals.length ? <code>{rawSignals.join(" / ")}</code> : null}</header>
            <dl>
              <div className="investigation-relationship-list__comparison"><dt>{metricLabel(item.metric)} · baseline → current</dt><dd><strong>{evidenceNumber(item.baseline)}</strong><span aria-hidden="true">→</span><strong>{evidenceNumber(item.current)}</strong></dd></div>
              {item.relationshipDirection || magnitude !== "Not supplied" ? <div><dt>Direction / magnitude</dt><dd>{displayLabel(item.relationshipDirection, "Changed")}{magnitude === "Not supplied" ? "" : ` · ${magnitude}`}</dd></div> : null}
              {baselineSamples !== null && baselineSamples !== undefined ? <div><dt>Paired samples</dt><dd>{baselineSamples} baseline · {currentSamples ?? "Unavailable"} current</dd></div> : null}
              {window ? <div><dt>Evidence window</dt><dd>{window}</dd></div> : null}
              {item.confidence ? <div><dt>Recorded support</dt><dd>{displayLabel(item.confidence)}</dd></div> : null}
            </dl>
          </li>
        );
      })}
    </ol>
  );
}

function SourceSignalList({ finding }) {
  const rawSignals = uniqueText([
    ...(finding.rawVariables ?? []),
    ...(finding.relationships ?? []).flatMap((item) => [item.rawSource, item.rawTarget]),
  ]);
  if (!rawSignals.length) return <p className="case-unavailable">No source signal identifiers were recorded.</p>;
  return <ul className="investigation-signal-list">{rawSignals.map((signal) => <li key={signal}><code>{signal}</code></li>)}</ul>;
}

function evidenceTrendPhrase(value) {
  return ({
    increasing: "Evidence support increasing",
    stable: "Evidence support stable",
    decreasing: "Evidence support decreasing",
    sudden: "Evidence increased suddenly",
    gradual: "Evidence building gradually",
    "stable shift": "Evidence stable",
    strengthening: "Evidence support increasing",
    weakening: "Evidence support decreasing",
    recovering: "Evidence recovering",
    recurring: "Evidence recurring",
    intermittent: "Evidence intermittent",
  })[String(value ?? "").trim().toLowerCase()] || `Support trend: ${String(value ?? "unavailable").trim().toLowerCase()}`;
}

function timelineLabel(event, timeZone) {
  if (event.periodLabel) return event.periodLabel;
  if (event.time) return formatLocalTimestamp(event.time, timeZone);
  if (event.start || event.end) return formatLocalTimestampRange(event.start, event.end, timeZone);
  return "Recorded period";
}

function CaseHeader({ eyebrow, finding, reviewRecord }) {
  return (
    <header className="case-header">
      <div><span className="forensic-kicker">{eyebrow}</span><p>{finding.system || finding.location?.label || "System not assigned"}</p><h1>{finding.title}</h1></div>
      <div className="case-header__state"><span>Current review state</span><strong>{reviewStateLabel(reviewRecord)}</strong></div>
    </header>
  );
}

function GuidanceList({ items, start = 1, compact = false }) {
  return <ol className="classification-guidance" start={start}>{items.map((item, index) => <li key={`${item.rank}-${item.check}`}><span>{item.rank || start + index}</span><div><strong>{item.check}</strong>{!compact && item.reason ? <p>{sentence(item.reason)}</p> : null}{!compact ? <small>{displayLabel(item.category)}</small> : null}</div></li>)}</ol>;
}

function RelationshipTimeline({ events, timeZone }) {
  if (!events.length) return <p className="case-unavailable">No source-bounded timeline milestones were recorded.</p>;
  return <ol className="classification-timeline">{events.map((event, index) => {
    const sourceTimestamp = event.time || [event.start, event.end].filter(Boolean).join(" → ");
    return <li key={`${event.eventType}-${index}`}><time dateTime={event.time || event.start || undefined} title={sourceTimestamp ? timestampTechnicalTitle(sourceTimestamp, timeZone) : undefined}>{timelineLabel(event, timeZone)}</time><strong>{event.title}</strong>{event.detail ? <p>{sentence(event.detail)}</p> : null}</li>;
  })}</ol>;
}

function ConditionEvolution({ finding }) {
  const trajectory = finding?.trajectory ?? {};
  const corroboration = finding?.corroboration ?? {};
  const comparable = finding?.comparableOperation ?? {};
  if (finding?.objectType !== "condition") return null;
  return (
    <>
      <section>
        <h2>Support trend</h2>
        <p className="case-lead">{evidenceTrendPhrase(finding.supportTrend || trajectory.state)}</p>
        {trajectory.evidence_window_duration ? <p>Evidence window: {trajectory.evidence_window_duration}</p> : null}
        {trajectory.corroboration_change ? <p>{sentence(trajectory.corroboration_change)}</p> : null}
        {trajectory.operational_explanation ? <p>{sentence(trajectory.operational_explanation)}</p> : null}
      </section>
      <section>
        <h2>Comparable operation</h2>
        {comparable.status === "supported" ? (
          <ul>
            <li>{comparable.comparable_period_count} comparable periods</li>
            <li><strong>Normal behavior:</strong> {comparable.normal_behavior}</li>
            <li><strong>Current behavior:</strong> {comparable.current_behavior}</li>
          </ul>
        ) : <p>{sentence(comparable.evidence_summary || "Comparable historical operation was not available.")}</p>}
        {corroboration.relationship_count ? <small>{corroboration.relationship_count} supporting relationships · {displayLabel(corroboration.corroboration_strength)} corroboration</small> : null}
      </section>
    </>
  );
}

function ReviewStateBlock({ finding, reviewRecord, onReviewAction, showActions = true }) {
  return (
    <div className="case-review-state">
      <dl>
        <div><dt>State</dt><dd>{reviewStateLabel(reviewRecord)}</dd></div>
        {reviewRecord?.reviewedAt ? <div><dt>Last reviewed</dt><dd>{reviewRecord.reviewedAt}</dd></div> : null}
        {reviewRecord?.owner ? <div><dt>Owner</dt><dd>{reviewRecord.owner}</dd></div> : null}
        {reviewRecord?.reason ? <div><dt>Known condition</dt><dd>{displayLabel(reviewRecord.reason)}</dd></div> : null}
        {reviewRecord?.priority ? <div><dt>Priority</dt><dd>{displayLabel(reviewRecord.priority)}</dd></div> : null}
        {reviewRecord?.assignment?.label ? <div><dt>Assignment</dt><dd>{reviewRecord.assignment.label}</dd></div> : null}
        {reviewRecord?.dueDate ? <div><dt>Due</dt><dd>{reviewRecord.dueDate}</dd></div> : null}
        {reviewRecord?.validationOutcome ? <div><dt>Validation</dt><dd>{displayLabel(reviewRecord.validationOutcome)}</dd></div> : null}
      </dl>
      {showActions ? <FindingReviewActions finding={finding} reviewRecord={reviewRecord} onAction={onReviewAction} /> : null}
    </div>
  );
}

function TechnicalAnalysisMetadata({ finding }) {
  const relationship = finding.relationships?.[0] ?? {};
  const metric = finding.comparison?.metric || relationship.metric || "Relationship coefficient";
  const identity = finding.technicalIdentity ?? {};
  const structuredRecordCount = finding.evidenceObjects.length;
  const observationCount = finding.supporting.length;
  return (
    <>
      <p className="technical-record-note">{structuredRecordCount
        ? `${structuredRecordCount} linked structured evidence ${structuredRecordCount === 1 ? "record" : "records"}; ${observationCount} supporting ${observationCount === 1 ? "observation" : "observations"}.`
        : `No structured evidence records are linked. ${observationCount} supporting ${observationCount === 1 ? "observation is" : "observations are"} shown in the evidence summary.`}</p>
      <dl className="classification-detail-grid classification-detail-grid--mode">
        <div><dt>Metric key</dt><dd>{metric}</dd></div>
        <div><dt>Baseline · raw</dt><dd>{finding.comparison.baselineValue ?? "Not supplied"}</dd></div>
        <div><dt>Current · raw</dt><dd>{finding.comparison.currentValue ?? "Not supplied"}</dd></div>
        <div><dt>Signed change · raw</dt><dd>{finding.comparison.signedChange ?? "Not supplied"}</dd></div>
        <div><dt>Absolute change · raw</dt><dd>{finding.comparison.absoluteChange ?? "Not supplied"}</dd></div>
        <div><dt>Linked structured records</dt><dd>{structuredRecordCount}</dd></div>
        <div><dt>Finding identity</dt><dd>{identity.findingId || finding.id}</dd></div>
        <div><dt>Workflow identity</dt><dd>{identity.workflowFindingId || "Not linked"}</dd></div>
        <div><dt>System identity</dt><dd>{identity.systemId || "Not supplied"}</dd></div>
        <div><dt>Asset identity</dt><dd>{identity.assetId || "Not supplied"}</dd></div>
        <div><dt>Source signals</dt><dd>{finding.rawVariables?.join(" / ") || [relationship.rawSource, relationship.rawTarget].filter(Boolean).join(" / ") || "Not supplied"}</dd></div>
      </dl>
    </>
  );
}

function EmptyCase({ onBack }) {
  return <div className="case-workspace"><button type="button" className="evidence-back" onClick={onBack}>Back to Operations Brief</button><section className="normal-summary"><span>Finding</span><h1>No active finding is available.</h1><p>Return to the Operations Brief to review the current evidence state.</p></section></div>;
}

export function FindingReviewWorkspace({ finding, reviewRecord, onReviewAction, onWorkflowSave, onWorkflowFeedback, onWorkflowResolve, onWorkflowReload, onOpenInvestigation, onBack }) {
  if (!finding) return <EmptyCase onBack={onBack} />;
  const presentation = finding.classificationPresentation ?? normalizeFindingPresentation(finding);
  const guidance = presentation.investigationGuidance.slice(0, 3);
  const insufficient = finding.status === "Evidence insufficient" || ["Deferred", "Withheld"].includes(finding.tier);
  const change = insufficient ? "A supported change cannot be shown from the available evidence." : finding.observedChange;
  const limit = finding.primaryLimitation || finding.certaintyLimit || finding.confidenceReason;
  const why = finding.whyItMatters || finding.visibleSupporting?.[0] || "Review the evidence boundary before deciding the next action.";
  return (
    <div className="case-workspace finding-review-workspace" data-testid="finding-review">
      <button type="button" className="evidence-back" onClick={onBack}>Back to Operations Brief</button>
      <CaseHeader eyebrow="Finding review" finding={finding} reviewRecord={reviewRecord} />
      <FindingClassificationSummary finding={finding} presentation={presentation} showDefinition={false} />
      <div className="case-sections case-sections--review">
        <section><h2>What changed</h2><p className="case-lead">{change}</p></section>
        <section><h2>Why this deserves attention</h2><p>{why}</p></section>
        <section><h2>Important limitations</h2><p>{limit || presentation.certaintyLimit}</p></section>
        <section><h2>What to check first</h2>{guidance.length ? <GuidanceList items={guidance} /> : <p>No evidence-linked check was recorded.</p>}</section>
      </div>
      <div className="case-primary-action"><div><span className="forensic-kicker">Need the full case?</span><strong>Open the relationship evidence and technical guidance.</strong></div><button type="button" className="forensic-button" onClick={() => onOpenInvestigation?.(finding)}>Open investigation</button></div>
      <section className="case-quick-actions" aria-labelledby="finding-actions-title"><div><span className="forensic-kicker">Review action</span><h2 id="finding-actions-title">Set the review state</h2></div><FindingReviewActions finding={finding} reviewRecord={reviewRecord} onAction={onReviewAction} /></section>
      <FindingWorkflowPanel finding={finding} workflow={reviewRecord} onSave={onWorkflowSave} onFeedback={onWorkflowFeedback} onResolve={onWorkflowResolve} onReload={onWorkflowReload} />
      <details className="case-classification-detail"><summary>Full classification reasoning</summary><ul>{presentation.reasons.map((item) => <li key={item}>{item}</li>)}</ul></details>
    </div>
  );
}

export function InvestigationWorkspace({ model, finding, reviewRecord, escalated = false, onReviewAction, onOpenEvidence, onTrace, onBack }) {
  if (!finding) return <EmptyCase onBack={onBack} />;
  const presentation = finding.classificationPresentation ?? normalizeFindingPresentation(finding);
  const relationship = finding.relationships[0] ?? model.relationships[0] ?? null;
  const limitations = uniqueText([...presentation.dataLimitations, ...finding.contradictions, ...finding.limitations, finding.confidenceReason]);
  const runId = runIdentity(model, finding);
  const timeZone = resolveDisplayTimeZone(model.facilityTimeZone);
  const graphRelationships = finding.relationships ?? [];
  const graphNodes = relationshipNodes(graphRelationships);
  return (
    <div className="case-workspace investigation-case-workspace" data-testid="investigation-workspace">
      <button type="button" className="evidence-back" onClick={onBack}>Back to finding</button>
      <CaseHeader eyebrow="Investigation" finding={finding} reviewRecord={reviewRecord} />
      {escalated ? <section className="case-escalation"><span>Prompt engineering review</span><strong>A persistent relationship change is supported across related signals.</strong><p>Verify source data and inspect the affected system boundary.</p></section> : null}
      <div className="case-primary-action case-primary-action--top"><div><span className="forensic-kicker">Evidence record</span><strong>Inspect source lineage and technical values.</strong></div><button type="button" className="forensic-button" onClick={() => onOpenEvidence?.(finding)}>Open evidence record</button></div>
      <div className="case-sections case-sections--investigation">
        <section><h2>Primary relationship comparison</h2><RelationshipComparison finding={finding} timeZone={timeZone} /></section>
        <section><h2>Relationships changed</h2><RelationshipEvidenceList finding={finding} timeZone={timeZone} /></section>
        <ConditionEvolution finding={finding} />
        <section><h2>{finding.objectType === "condition" ? "Condition timeline" : "Relationship timeline"}</h2><p className="investigation-timezone">Displayed in {timeZone}. Exact source timestamps remain available in timeline tooltips and lineage.</p><RelationshipTimeline events={presentation.timeline} timeZone={timeZone} /></section>
        <section><h2>Operating context</h2><dl className="classification-detail-grid classification-detail-grid--mode"><div><dt>Baseline mode</dt><dd>{presentation.operatingMode.baseline}</dd></div><div><dt>Current mode</dt><dd>{presentation.operatingMode.recent}</dd></div><div><dt>Comparability</dt><dd>{presentation.operatingMode.match}</dd></div><div><dt>Context evidence</dt><dd>{presentation.operatingMode.confidence}</dd></div></dl>{presentation.operatingMode.reasons.length ? <ul>{presentation.operatingMode.reasons.map((item) => <li key={item}>{item}</li>)}</ul> : null}</section>
        <section><h2>Supporting evidence records</h2>{finding.supporting.length ? <ul>{finding.supporting.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No supporting observation was supplied.</p>}</section>
        <section><h2>Data quality and comparability limits</h2>{limitations.length ? <ul>{limitations.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No additional data limitations were recorded.</p>}{presentation.sensorHealth.length ? <ul className="classification-sensor-list">{presentation.sensorHealth.map((sensor) => <li key={sensor.signal}><strong>{displayLabel(sensor.signal)} · {displayLabel(sensor.health)}</strong>{sensor.conditions.length ? <ul>{sensor.conditions.map((condition, index) => <li key={`${condition.type}-${index}`}>{displayLabel(condition.type)}: {condition.evidence || "No supporting detail was recorded."}</li>)}</ul> : null}</li>)}</ul> : null}</section>
        <section><h2>Source signals and lineage</h2><SourceSignalList finding={finding} /><EvidenceLineage finding={finding} relationship={relationship} result={model.result} /></section>
      </div>
      {graphRelationships.length > 1 ? <details className="case-classification-detail"><summary>Relationship evidence map</summary><RelationshipGraph nodes={graphNodes} relationships={graphRelationships} timeLabel={comparisonWindowLabel(finding.comparison.current, timeZone)} /></details> : null}
      <SiiEvidenceRecord evidence={model.siiEvidence ?? finding.siiEvidence} />
      <div className="engineering-investigation-disclosures" aria-label="Additional investigation detail">
        <details><summary>Alternative explanations</summary>{presentation.alternativeExplanations.length ? <ul>{presentation.alternativeExplanations.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No alternative explanations were recorded.</p>}</details>
        <details><summary>Certainty limits</summary><p>{presentation.certaintyLimit}</p></details>
        <details><summary>Audit, workflow, and replay</summary><ReviewStateBlock finding={finding} reviewRecord={reviewRecord} onReviewAction={onReviewAction} /><dl className="classification-detail-grid"><div><dt>Evidence run</dt><dd>{runId ?? "Not persisted"}</dd></div><div><dt>Review outcome</dt><dd>{finding.outcome ? JSON.stringify(finding.outcome) : "No persisted review outcome"}</dd></div><div><dt>Generated</dt><dd><time dateTime={finding.generatedAt || undefined} title={timestampTechnicalTitle(finding.generatedAt, timeZone)}>{formatLocalTimestamp(finding.generatedAt, timeZone)}</time></dd></div></dl><button type="button" className="forensic-button forensic-button--secondary" onClick={onTrace}>Open trace mode</button></details>
        <details><summary>Full classification reasoning</summary><p>{presentation.meaning}</p><ul>{presentation.reasons.map((item) => <li key={item}>{item}</li>)}</ul></details>
        <details><summary>Technical analysis metadata</summary><TechnicalAnalysisMetadata finding={finding} /></details>
        {finding.objectType === "condition" ? <details><summary>Relationship details</summary>{finding.relationships.length ? <ul>{finding.relationships.map((item) => <li key={item.id || item.label}>{item.label}</li>)}</ul> : <p>No supporting relationship detail was recorded.</p>}{finding.conflictingRelationships.length ? <><h3>Conflicting evidence</h3><ul>{finding.conflictingRelationships.map((item) => <li key={item.relationship_id || item.id}>{(item.signals || item.columns || []).join(" / ")}</li>)}</ul></> : null}{finding.uncertainRelationships.length ? <><h3>Uncertain evidence</h3><ul>{finding.uncertainRelationships.map((item) => <li key={item.relationship_id || item.id}>{(item.signals || item.columns || []).join(" / ")}</li>)}</ul></> : null}</details> : null}
      </div>
    </div>
  );
}

export function EvidenceRecordWorkspace({ model, finding, reviewRecord, apiFetch, onTrace, onBack }) {
  if (!finding) return <EmptyCase onBack={onBack} />;
  const relationship = finding.relationships[0] ?? model.relationships[0] ?? null;
  const runId = runIdentity(model, finding);
  const packageId = packageIdentity(model);
  const timeZone = resolveDisplayTimeZone(model.facilityTimeZone);
  return (
    <div className="case-workspace evidence-record-workspace" data-testid="evidence-record">
      <button type="button" className="evidence-back" onClick={onBack}>Back to investigation</button>
      <CaseHeader eyebrow="Evidence record" finding={finding} reviewRecord={reviewRecord} />
      <div className="evidence-record-grid">
        <section><h2>Supporting evidence</h2>{finding.supporting.length ? <ul>{finding.supporting.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No supporting observation was supplied.</p>}</section>
        <section><h2>Relationship comparison</h2><RelationshipComparison finding={finding} timeZone={timeZone} /></section>
        <section><h2>Source lineage</h2><EvidenceLineage finding={finding} relationship={relationship} result={model.result} /></section>
        <section><h2>Record context</h2><p className="investigation-timezone">Displayed in {timeZone}. Exact values remain in technical identifiers.</p><dl className="classification-detail-grid classification-detail-grid--mode"><div><dt>Baseline window</dt><dd>{comparisonWindowLabel(finding.comparison.baseline, timeZone)}</dd></div><div><dt>Current window</dt><dd>{comparisonWindowLabel(finding.comparison.current, timeZone)}</dd></div><div className="classification-detail-grid__wide"><dt>Generated</dt><dd><time dateTime={finding.generatedAt || undefined} title={timestampTechnicalTitle(finding.generatedAt, timeZone)}>{formatLocalTimestamp(finding.generatedAt, timeZone)}</time></dd></div></dl></section>
      </div>
      <RelatedEvidencePackages packageId={packageId} apiFetch={apiFetch} />
      <section className="evidence-record-actions"><EvidencePackageExport runId={runId} apiFetch={apiFetch} disabled={!runId} /><button type="button" className="forensic-button forensic-button--secondary" onClick={onTrace}>Open trace mode</button></section>
      <SiiEvidenceRecord evidence={model.siiEvidence ?? finding.siiEvidence} />
      <details className="case-classification-detail"><summary>Technical values and identifiers</summary><dl className="classification-detail-grid classification-detail-grid--mode"><div><dt>Evidence run</dt><dd>{runId ?? "Not persisted"}</dd></div><div><dt>Evidence package</dt><dd>{packageId ?? "Not persisted"}</dd></div><div className="classification-detail-grid__wide"><dt>Generated timestamp</dt><dd>{finding.generatedAt || "Not supplied"}</dd></div></dl><TechnicalAnalysisMetadata finding={finding} /></details>
      <details className="case-classification-detail"><summary>Audit history</summary><ReviewStateBlock finding={finding} reviewRecord={reviewRecord} showActions={false} /><p>{finding.outcome ? JSON.stringify(finding.outcome) : "No persisted review outcome was recorded."}</p></details>
    </div>
  );
}
