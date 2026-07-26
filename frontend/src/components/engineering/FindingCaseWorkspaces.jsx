import React from "react";
import { normalizeFindingPresentation } from "../../viewModels/operatorFinding";
import { reviewStateLabel } from "../../viewModels/findingReviewState";
import FindingClassificationSummary from "../operational/FindingClassificationSummary";
import EvidenceLineage from "./EvidenceLineage";
import EvidencePackageExport from "./EvidencePackageExport";
import FindingReviewActions from "./FindingReviewActions";

function runIdentity(model, finding) {
  return finding?.runId ?? model?.result?.run_id ?? model?.result?.job_id ?? model?.result?.upload_id ?? null;
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

function timelineLabel(event) {
  if (event.periodLabel) return event.periodLabel;
  if (event.time) return event.time;
  if (event.start && event.end) return `${event.start} to ${event.end}`;
  if (event.start) return `From ${event.start}`;
  if (event.end) return `Through ${event.end}`;
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

function GuidanceList({ items, start = 1 }) {
  return <ol className="classification-guidance" start={start}>{items.map((item, index) => <li key={`${item.rank}-${item.check}`}><span>{item.rank || start + index}</span><div><strong>{item.check}</strong>{item.reason ? <p>{sentence(item.reason)}</p> : null}<small>{displayLabel(item.category)}</small></div></li>)}</ol>;
}

function RelationshipTimeline({ events }) {
  if (!events.length) return <p className="case-unavailable">No source-bounded timeline milestones were recorded.</p>;
  return <ol className="classification-timeline">{events.map((event, index) => <li key={`${event.eventType}-${index}`}><time>{timelineLabel(event)}</time><strong>{event.title}</strong>{event.detail ? <p>{event.detail}</p> : null}</li>)}</ol>;
}

function ConditionEvolution({ finding }) {
  const trajectory = finding?.trajectory ?? {};
  const corroboration = finding?.corroboration ?? {};
  const comparable = finding?.comparableOperation ?? {};
  if (finding?.objectType !== "condition") return null;
  return (
    <>
      <section>
        <h2>Trajectory</h2>
        <p className="case-lead">{displayLabel(trajectory.state, "Unavailable")}</p>
        {trajectory.observed_for ? <p>{trajectory.observed_for}</p> : null}
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
        ) : <p>{comparable.evidence_summary || "Comparable historical operation was not available."}</p>}
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
      </dl>
      {showActions ? <FindingReviewActions finding={finding} reviewRecord={reviewRecord} onAction={onReviewAction} /> : null}
    </div>
  );
}

function EmptyCase({ onBack }) {
  return <div className="case-workspace"><button type="button" className="evidence-back" onClick={onBack}>Back to Operations Brief</button><section className="normal-summary"><span>Finding</span><h1>No active finding is available.</h1><p>All monitored relationships remain within the current review boundary.</p></section></div>;
}

export function FindingReviewWorkspace({ finding, reviewRecord, onReviewAction, onOpenInvestigation, onBack }) {
  if (!finding) return <EmptyCase onBack={onBack} />;
  const presentation = finding.classificationPresentation ?? normalizeFindingPresentation(finding);
  const guidance = presentation.investigationGuidance.slice(0, 3);
  const keyEvidence = finding.visibleSupporting?.slice(1, 3) ?? [];
  const why = uniqueText([sentence(finding.whyItMatters), presentation.persistence.persistent ? presentation.persistence.summary : ""]);
  return (
    <div className="case-workspace finding-review-workspace" data-testid="finding-review">
      <button type="button" className="evidence-back" onClick={onBack}>Back to Operations Brief</button>
      <CaseHeader eyebrow="Finding review" finding={finding} reviewRecord={reviewRecord} />
      <FindingClassificationSummary finding={finding} presentation={presentation} showDefinition={false} />
      <section className="case-quick-actions" aria-labelledby="finding-actions-title"><div><span className="forensic-kicker">Fast actions</span><h2 id="finding-actions-title">Set the review state</h2></div><FindingReviewActions finding={finding} reviewRecord={reviewRecord} onAction={onReviewAction} /></section>
      <div className="case-sections case-sections--review">
        <section><h2>What changed</h2><p className="case-lead">{finding.observedChange}</p></section>
        <section><h2>Why it deserves attention</h2>{why.length ? <ul>{why.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No additional explanation was recorded.</p>}</section>
        <ConditionEvolution finding={finding} />
        <section><h2>What to check first</h2>{guidance.length ? <GuidanceList items={guidance} /> : <p>No evidence-linked check was recorded.</p>}</section>
        <section><h2>{finding.objectType === "condition" ? "Condition timeline" : "Relationship timeline"}</h2><RelationshipTimeline events={presentation.timeline} /></section>
        <section><h2>Key evidence</h2>{keyEvidence.length ? <ul>{keyEvidence.map((item) => <li key={item}>{item}</li>)}</ul> : <p>{finding.comparisonSummary || "Review the supporting relationship evidence."}</p>}</section>
      </div>
      <div className="case-primary-action"><div><span className="forensic-kicker">Need the full case?</span><strong>Open the relationship evidence and technical guidance.</strong></div><button type="button" className="forensic-button" onClick={() => onOpenInvestigation?.(finding)}>Open investigation</button></div>
      <details className="case-classification-detail"><summary>Full classification reasoning</summary><p>{presentation.meaning}</p><ul>{presentation.reasons.map((item) => <li key={item}>{item}</li>)}</ul></details>
    </div>
  );
}

export function InvestigationWorkspace({ model, finding, reviewRecord, escalated = false, onReviewAction, onOpenEvidence, onTrace, onBack }) {
  if (!finding) return <EmptyCase onBack={onBack} />;
  const presentation = finding.classificationPresentation ?? normalizeFindingPresentation(finding);
  const relationship = finding.relationships[0] ?? model.relationships[0] ?? null;
  const guidance = presentation.investigationGuidance;
  const limitations = uniqueText([...presentation.dataLimitations, ...finding.contradictions, ...finding.limitations, finding.confidenceReason]);
  const runId = runIdentity(model, finding);
  return (
    <div className="case-workspace investigation-case-workspace" data-testid="investigation-workspace">
      <button type="button" className="evidence-back" onClick={onBack}>Back to finding</button>
      <CaseHeader eyebrow="Investigation" finding={finding} reviewRecord={reviewRecord} />
      {escalated ? <section className="case-escalation"><span>Prompt engineering review</span><strong>A persistent relationship change is supported across related signals.</strong><p>Verify source data and inspect the affected system boundary.</p></section> : null}
      <div className="case-primary-action case-primary-action--top"><div><span className="forensic-kicker">Evidence record</span><strong>Inspect source lineage and technical values.</strong></div><button type="button" className="forensic-button" onClick={() => onOpenEvidence?.(finding)}>Open evidence record</button></div>
      <div className="case-sections case-sections--investigation">
        <section><h2>Finding summary</h2><p className="case-lead">{finding.comparisonSummary}</p>{finding.location?.label ? <p>{finding.location.label}</p> : null}</section>
        <ConditionEvolution finding={finding} />
        <section><h2>{finding.objectType === "condition" ? "Condition timeline" : "Relationship timeline"}</h2><RelationshipTimeline events={presentation.timeline} /></section>
        <section><h2>Supporting evidence</h2>{finding.supporting.length ? <ul>{finding.supporting.slice(0, 3).map((item) => <li key={item}>{item}</li>)}</ul> : <p>No supporting observation was supplied.</p>}{finding.supporting.length > 3 ? <details className="evidence-section__more"><summary>Show all supporting evidence</summary><ul>{finding.supporting.slice(3).map((item) => <li key={item}>{item}</li>)}</ul></details> : null}</section>
        <section><h2>Investigation guidance</h2>{guidance.length ? <GuidanceList items={guidance.slice(0, 3)} /> : <p>No evidence-linked guidance was recorded.</p>}{guidance.length > 3 ? <details className="evidence-section__more"><summary>Show all checks</summary><GuidanceList items={guidance.slice(3)} start={4} /></details> : null}</section>
        <section><h2>Current review state</h2><ReviewStateBlock finding={finding} reviewRecord={reviewRecord} onReviewAction={onReviewAction} /></section>
      </div>
      <div className="engineering-investigation-disclosures" aria-label="Additional investigation detail">
        <details><summary>Operating-mode evidence</summary><dl className="classification-detail-grid classification-detail-grid--mode"><div><dt>Baseline mode</dt><dd>{presentation.operatingMode.baseline}</dd></div><div><dt>Recent mode</dt><dd>{presentation.operatingMode.recent}</dd></div><div><dt>Mode match</dt><dd>{presentation.operatingMode.match}</dd></div><div><dt>Comparison confidence</dt><dd>{presentation.operatingMode.confidence}</dd></div></dl>{presentation.operatingMode.reasons.length ? <ul>{presentation.operatingMode.reasons.map((item) => <li key={item}>{item}</li>)}</ul> : null}</details>
        <details><summary>Sensor-health evidence</summary><dl className="classification-detail-grid"><div><dt>Data confidence</dt><dd>{presentation.dataConfidence.rating}</dd></div><div><dt>Summary</dt><dd>{presentation.dataConfidence.summary}</dd></div></dl>{presentation.sensorHealth.length ? <ul className="classification-sensor-list">{presentation.sensorHealth.map((sensor) => <li key={sensor.signal}><strong>{displayLabel(sensor.signal)} · {displayLabel(sensor.health)}</strong>{sensor.conditions.length ? <ul>{sensor.conditions.map((condition, index) => <li key={`${condition.type}-${index}`}>{displayLabel(condition.type)}: {condition.evidence || "No supporting detail was recorded."}</li>)}</ul> : null}</li>)}</ul> : <p>No sensor-health conditions were recorded.</p>}</details>
        <details><summary>Alternative explanations</summary>{presentation.alternativeExplanations.length ? <ul>{presentation.alternativeExplanations.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No alternative explanations were recorded.</p>}</details>
        <details><summary>Certainty limits</summary><p>{presentation.certaintyLimit}</p></details>
        <details><summary>Data limitations</summary>{limitations.length ? <ul>{limitations.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No additional data limitations were recorded.</p>}</details>
        <details><summary>Source lineage</summary><EvidenceLineage finding={finding} relationship={relationship} result={model.result} /><dl className="classification-detail-grid classification-detail-grid--mode"><div><dt>Baseline window</dt><dd>{finding.comparison.baseline}</dd></div><div><dt>Current window</dt><dd>{finding.comparison.current}</dd></div><div><dt>Evidence run</dt><dd>{runId ?? "Not persisted"}</dd></div><div><dt>Generated</dt><dd>{finding.generatedAt || "Not supplied"}</dd></div></dl></details>
        <details><summary>Audit and replay information</summary><dl className="classification-detail-grid"><div><dt>Evidence run</dt><dd>{runId ?? "Not persisted"}</dd></div><div><dt>Review outcome</dt><dd>{finding.outcome ? JSON.stringify(finding.outcome) : "No persisted review outcome"}</dd></div></dl><button type="button" className="forensic-button forensic-button--secondary" onClick={onTrace}>Open trace mode</button></details>
        <details><summary>Full classification reasoning</summary><p>{presentation.meaning}</p><ul>{presentation.reasons.map((item) => <li key={item}>{item}</li>)}</ul></details>
        <details><summary>Technical analysis metadata</summary><dl className="classification-detail-grid classification-detail-grid--mode"><div><dt>Baseline relationship value</dt><dd>{finding.comparison.baselineValue ?? "Not supplied"}</dd></div><div><dt>Current relationship value</dt><dd>{finding.comparison.currentValue ?? "Not supplied"}</dd></div><div><dt>Relationship delta</dt><dd>{finding.comparison.delta ?? "Not supplied"}</dd></div><div><dt>Evidence records</dt><dd>{finding.evidenceObjects.length}</dd></div></dl></details>
        {finding.objectType === "condition" ? <details><summary>Relationship details</summary>{finding.relationships.length ? <ul>{finding.relationships.map((item) => <li key={item.id || item.label}>{item.label}</li>)}</ul> : <p>No supporting relationship detail was recorded.</p>}{finding.conflictingRelationships.length ? <><h3>Conflicting evidence</h3><ul>{finding.conflictingRelationships.map((item) => <li key={item.relationship_id || item.id}>{(item.signals || item.columns || []).join(" / ")}</li>)}</ul></> : null}{finding.uncertainRelationships.length ? <><h3>Uncertain evidence</h3><ul>{finding.uncertainRelationships.map((item) => <li key={item.relationship_id || item.id}>{(item.signals || item.columns || []).join(" / ")}</li>)}</ul></> : null}</details> : null}
      </div>
    </div>
  );
}

export function EvidenceRecordWorkspace({ model, finding, reviewRecord, apiFetch, onTrace, onBack }) {
  if (!finding) return <EmptyCase onBack={onBack} />;
  const relationship = finding.relationships[0] ?? model.relationships[0] ?? null;
  const runId = runIdentity(model, finding);
  return (
    <div className="case-workspace evidence-record-workspace" data-testid="evidence-record">
      <button type="button" className="evidence-back" onClick={onBack}>Back to investigation</button>
      <CaseHeader eyebrow="Evidence record" finding={finding} reviewRecord={reviewRecord} />
      <div className="evidence-record-grid">
        <section><h2>Supporting evidence</h2>{finding.supporting.length ? <ul>{finding.supporting.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No supporting observation was supplied.</p>}</section>
        <section><h2>Source lineage</h2><EvidenceLineage finding={finding} relationship={relationship} result={model.result} /></section>
        <section><h2>Record context</h2><dl className="classification-detail-grid classification-detail-grid--mode"><div><dt>Baseline window</dt><dd>{finding.comparison.baseline}</dd></div><div><dt>Current window</dt><dd>{finding.comparison.current}</dd></div><div><dt>Evidence run</dt><dd>{runId ?? "Not persisted"}</dd></div><div><dt>Generated</dt><dd>{finding.generatedAt || "Not supplied"}</dd></div></dl></section>
        <section><h2>Technical values</h2><dl className="classification-detail-grid classification-detail-grid--mode"><div><dt>Baseline relationship value</dt><dd>{finding.comparison.baselineValue ?? "Not supplied"}</dd></div><div><dt>Current relationship value</dt><dd>{finding.comparison.currentValue ?? "Not supplied"}</dd></div><div><dt>Relationship delta</dt><dd>{finding.comparison.delta ?? "Not supplied"}</dd></div><div><dt>Evidence records</dt><dd>{finding.evidenceObjects.length}</dd></div></dl></section>
      </div>
      <section className="evidence-record-actions"><EvidencePackageExport runId={runId} apiFetch={apiFetch} disabled={!runId} /><button type="button" className="forensic-button forensic-button--secondary" onClick={onTrace}>Open trace mode</button></section>
      <details className="case-classification-detail"><summary>Audit history</summary><ReviewStateBlock finding={finding} reviewRecord={reviewRecord} showActions={false} /><p>{finding.outcome ? JSON.stringify(finding.outcome) : "No persisted review outcome was recorded."}</p></details>
    </div>
  );
}
