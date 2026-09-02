import React, { useEffect, useMemo, useState } from "react";
import { getTelemetryAnalysisResultLineage } from "../../services/api/telemetryConnectionsApi";
import EvidenceDashboard from "./EvidenceDashboard";
import EvidencePackageExport from "./EvidencePackageExport";
import RelatedEvidencePackages from "./RelatedEvidencePackages";
import { projectEvidenceDashboardSummary } from "./evidenceDashboardProjection";

const ASSESSMENT_LABELS = Object.freeze([
  ["changeConfidence", "Change confidence"],
  ["evidenceQuality", "Evidence quality"],
  ["causeAttribution", "Cause / attribution"],
  ["persistence", "Persistence"],
  ["operatingContext", "Operating context"],
  ["corroboration", "Corroboration"],
  ["evidenceSufficiency", "Evidence sufficiency"],
]);

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

function JsonValue({ value }) {
  if (value === null || value === undefined) return <p className="case-unavailable">Not supplied.</p>;
  if (["string", "number", "boolean"].includes(typeof value)) return <p>{String(value)}</p>;
  return <pre className="evidence-record-json" tabIndex={0}>{JSON.stringify(value, null, 2)}</pre>;
}

function ProjectionUnavailable({ projection, onBack }) {
  return (
    <div className="case-workspace scoped-route-state">
      <span className="forensic-kicker">Operations Brief</span>
      <h1>{projection?.title ?? "Result unavailable"}</h1>
      <p>{projection?.explanation ?? "This result is unavailable in the current analysis record."}</p>
      <button type="button" className="forensic-button forensic-button--secondary" onClick={onBack}>Back to results</button>
    </div>
  );
}

function CaseHeader({ eyebrow, header }) {
  return (
    <header className="case-header">
      <div><span className="forensic-kicker">{eyebrow}</span><p>{header?.systemContext || "System not assigned"}</p><h1>{header?.title || "Finding unavailable"}</h1></div>
      <div className="case-header__state"><span>Current review state</span><strong>{header?.reviewState || "Not reviewed"}</strong></div>
    </header>
  );
}

function ChannelState({ state }) {
  if (!state || state.state === "available") return null;
  return <p className="case-unavailable">{state.reason || "This evidence channel was not supplied for this analysis."}</p>;
}

function ScopeNote({ scopeLabel, sourcePath, qualification = null }) {
  const bounded = qualification && (qualification.truncated || qualification.transported === false);
  return <div className="evidence-scope-note"><strong>{scopeLabel}</strong>{sourcePath ? <code>{sourcePath}</code> : null}{qualification ? <small>{bounded ? "Bounded projection; the canonical artifact contains additional exact facts." : "Complete for this projected source channel."}</small> : null}</div>;
}

function ProjectionQualification({ qualification, depth }) {
  if (!qualification) return null;
  const referenceMetadata = qualification.referenceMetadata && typeof qualification.referenceMetadata === "object" ? qualification.referenceMetadata : {};
  return (
    <section className="evidence-projection-qualification" data-truncated={qualification.truncated ? "true" : "false"}>
      <h2>Canonical source qualification</h2>
      <p>{qualification.truncated ? "This product view is a bounded projection. Listed sources were truncated or withheld from transport; the immutable canonical artifact remains authoritative." : "The transported canonical sources are complete within their recorded projection bounds."}</p>
      <dl className="classification-detail-grid classification-detail-grid--mode">
        <div><dt>Projection contract</dt><dd>{qualification.contractVersion || "Not supplied"}</dd></div>
        <div><dt>Canonical result</dt><dd>{qualification.canonicalResultId || "Not supplied"}</dd></div>
        {depth === "evidence" ? <div className="classification-detail-grid__wide"><dt>Canonical digest</dt><dd><code>{qualification.canonicalPayloadDigest || "Not supplied"}</code></dd></div> : null}
        <div className="classification-detail-grid__wide"><dt>Partial source paths</dt><dd>{qualification.truncatedSources?.join(" / ") || "None"}</dd></div>
      </dl>
      <h3>Reference / model identity</h3>
      {Object.keys(referenceMetadata).length ? <JsonValue value={referenceMetadata} /> : <p className="case-unavailable">The engine did not supply a separate reference or model identity.</p>}
    </section>
  );
}

function RelationshipComparison({ relationship }) {
  if (!relationship) return <p className="case-unavailable">A numeric relationship comparison was not recorded for this finding.</p>;
  const magnitude = evidenceNumber(relationship.magnitude);
  return (
    <div className="evidence-comparison">
      <p className="evidence-comparison__summary">{relationship.metricChannel} {displayLabel(relationship.direction, "changed").toLowerCase()}{magnitude === "Not supplied" ? "" : ` by ${magnitude}`} from the learned baseline.</p>
      <dl>
        <div><dt>Baseline</dt><dd>{evidenceNumber(relationship.baseline)}<small>{relationship.baselineSamples === null ? "Sample count not supplied" : `${relationship.baselineSamples} paired samples`}</small></dd></div>
        <div><dt>Current</dt><dd>{evidenceNumber(relationship.current)}<small>{relationship.currentSamples === null ? "Sample count not supplied" : `${relationship.currentSamples} paired samples`}</small></dd></div>
        <div><dt>Change</dt><dd>{evidenceNumber(relationship.signedChange, { signed: true })}<small>{displayLabel(relationship.direction, "Comparison recorded")}</small></dd></div>
      </dl>
    </div>
  );
}

function RelationshipList({ relationships }) {
  if (!relationships?.length) return <p className="case-unavailable">No finding-owned relationship comparison was recorded.</p>;
  return (
    <ol className="investigation-relationship-list">
      {relationships.map((item, index) => (
        <li key={item.id || index}>
          <header><span>Relationship {index + 1}</span><strong>{item.source.display} ↔ {item.target.display}</strong><code>{[item.source.sourceId, item.target.sourceId].filter(Boolean).join(" / ")}</code></header>
          <dl>
            <div className="investigation-relationship-list__comparison"><dt>{item.metricChannel} · baseline → current</dt><dd><strong>{evidenceNumber(item.baseline)}</strong><span aria-hidden="true">→</span><strong>{evidenceNumber(item.current)}</strong></dd></div>
            <div><dt>Direction / magnitude</dt><dd>{displayLabel(item.direction)}{item.magnitude === null ? "" : ` · ${evidenceNumber(item.magnitude)}`}</dd></div>
            <div><dt>Paired samples</dt><dd>{item.baselineSamples ?? "Unavailable"} baseline · {item.currentSamples ?? "Unavailable"} current</dd></div>
            <div><dt>Persistence / support</dt><dd>{[item.persistence, item.support].filter(Boolean).join(" · ") || "Unavailable"}</dd></div>
            {item.windows?.length ? <div className="classification-detail-grid__wide"><dt>Evidence windows</dt><dd>{item.windows.map((window) => [window.baselineStart, window.baselineEnd, window.currentStart, window.currentEnd].filter(Boolean).join(" → ")).filter(Boolean).join("; ") || "Unavailable"}</dd></div> : null}
          </dl>
        </li>
      ))}
    </ol>
  );
}

export function FindingReviewWorkspace({ projection, onOpenInvestigation, onBack }) {
  if (!projection || projection.variant === "unavailable") return <ProjectionUnavailable projection={projection} onBack={onBack} />;
  const dashboardSummary = projectEvidenceDashboardSummary(projection);
  return (
    <div className="case-workspace finding-review-workspace" data-testid="finding-review">
      <button type="button" className="evidence-back" onClick={onBack}>Back to Operations Brief</button>
      <EvidenceDashboard summary={dashboardSummary} variant={projection.variant} />
      <div className="case-sections case-sections--review evidence-next-steps">
        <section><h2>What changed</h2><p className="case-lead">{projection.whatChanged}</p></section>
        <section><h2>Why this deserves attention</h2><ul>{projection.whyAttention.map((reason) => <li key={reason}>{reason}</li>)}</ul></section>
        <section className="evidence-assessment evidence-assessment--secondary"><h2>Evidence assessment</h2><dl>{ASSESSMENT_LABELS.map(([key, assessmentLabel]) => <div key={key} data-state={projection.assessment[key].state}><dt>{assessmentLabel}</dt><dd>{projection.assessment[key].value}</dd></div>)}</dl></section>
        <section><h2>Important limitation</h2><p>{projection.materialLimitation || "No material limitation was recorded at this review depth."}</p></section>
        <section><h2>Where to investigate next</h2>{projection.checks.length ? <ol>{projection.checks.map((item) => <li key={item.label}>{item.label}</li>)}</ol> : <p>No evidence-linked investigation check was recorded.</p>}</section>
      </div>
      {projection.primaryAction ? <div className="case-primary-action"><div><span className="forensic-kicker">Investigation</span><strong>Inspect comparisons, persistence, context, and source signals.</strong></div><button type="button" className="forensic-button" onClick={() => onOpenInvestigation?.(projection.identity.findingKey)}>{projection.primaryAction.label}</button></div> : null}
    </div>
  );
}

export function InvestigationWorkspace({ projection, onOpenEvidence, onBack }) {
  if (!projection || projection.variant === "unavailable") return <ProjectionUnavailable projection={projection} onBack={onBack} />;
  const analysisScoped = projection.identity?.scope === "analysis";
  return (
    <div className="case-workspace investigation-case-workspace" data-testid="investigation-workspace">
      <button type="button" className="evidence-back" onClick={onBack}>{analysisScoped ? "Back to results" : "Back to finding"}</button>
      <CaseHeader eyebrow="Investigation" header={projection.header} />
      <div className="case-primary-action case-primary-action--top"><div><span className="forensic-kicker">Evidence record</span><strong>Inspect exact transported facts, canonical references, provenance, and audit history.</strong></div><button type="button" className="forensic-button" onClick={() => onOpenEvidence?.(projection.identity.findingKey)}>{projection.primaryAction.label}</button></div>
      <div className="case-sections case-sections--investigation">
        <section><h2>Primary relationship comparison</h2><RelationshipComparison relationship={projection.primaryComparison} /></section>
        <section><h2>Relationship evidence</h2><RelationshipList relationships={projection.relationships} /></section>
        <section><h2>Persistence and confidence</h2><ChannelState state={projection.persistence.state} /><dl className="classification-detail-grid classification-detail-grid--mode"><div><dt>Persistence</dt><dd>{projection.persistence.summary || "Unavailable"}</dd></div><div><dt>Support trend</dt><dd>{projection.persistence.supportTrend || "Unavailable"}</dd></div><div className="classification-detail-grid__wide"><dt>Window</dt><dd>{projection.persistence.windowDescription || "Unavailable"}</dd></div></dl></section>
        <section><h2>Operating context</h2><ChannelState state={projection.operatingContext.state} /><dl className="classification-detail-grid classification-detail-grid--mode"><div><dt>Baseline mode</dt><dd>{projection.operatingContext.baselineMode || "Unavailable"}</dd></div><div><dt>Current mode</dt><dd>{projection.operatingContext.currentMode || "Unavailable"}</dd></div><div><dt>Comparability</dt><dd>{projection.operatingContext.comparability || "Unavailable"}</dd></div></dl>{projection.operatingContext.reasons.length ? <ul>{projection.operatingContext.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul> : null}</section>
        <section><h2>System evidence channels</h2><div className="investigation-channel-list">{projection.systemEvidence.map((channel) => <article key={channel.key}><h3>{channel.label}</h3><ScopeNote scopeLabel={channel.scopeLabel} sourcePath={channel.sourcePath} qualification={channel.qualification} /><ChannelState state={channel.state} />{channel.summary ? <p>{channel.summary}</p> : null}{channel.metrics.length ? <dl>{channel.metrics.map((metric) => <div key={metric.label}><dt>{metric.label}</dt><dd>{metric.value}</dd></div>)}</dl> : null}</article>)}</div></section>
        <section><h2>Data quality and comparability</h2><ChannelState state={projection.dataQuality.state} />{projection.dataQuality.summary ? <p>{projection.dataQuality.summary}</p> : null}{projection.dataQuality.limitations.length ? <ul>{projection.dataQuality.limitations.map((item) => <li key={item}>{item}</li>)}</ul> : null}{projection.dataQuality.signalHealth.length ? <dl className="classification-detail-grid">{projection.dataQuality.signalHealth.map((item) => <div key={`${item.signal}-${item.status}`}><dt>{item.signal}</dt><dd>{item.status}</dd></div>)}</dl> : null}</section>
        <section><h2>Timeline</h2>{projection.timeline.length ? <ol>{projection.timeline.map((item, index) => <li key={`${item.label}-${index}`}><strong>{item.label}</strong>{item.detail ? ` · ${item.detail}` : ""}</li>)}</ol> : <p className="case-unavailable">No source-bounded timeline was recorded.</p>}</section>
        <section><h2>Source signals and lineage</h2>{projection.sourceSignals.length ? <ul className="investigation-signal-list">{projection.sourceSignals.map((signal) => <li key={signal.sourceId}><span>{signal.display}</span><code>{signal.sourceId}</code></li>)}</ul> : <p className="case-unavailable">No source signal identifiers were recorded.</p>}<dl className="classification-detail-grid classification-detail-grid--mode"><div><dt>Source</dt><dd>{projection.lineageSummary.source || "Unavailable"}</dd></div><div><dt>Baseline window</dt><dd>{projection.lineageSummary.baselineWindow || "Unavailable"}</dd></div><div><dt>Current window</dt><dd>{projection.lineageSummary.currentWindow || "Unavailable"}</dd></div><div className="classification-detail-grid__wide"><dt>Evidence references</dt><dd>{projection.lineageSummary.evidenceRefs.join(" / ") || "Unavailable"}</dd></div></dl></section>
        <ProjectionQualification qualification={projection.projectionQualification} depth="investigation" />
      </div>
    </div>
  );
}

function RecordList({ items, empty }) {
  return items?.length ? <ul>{items.map((item, index) => <li key={index}><JsonValue value={item} /></li>)}</ul> : <p className="case-unavailable">{empty}</p>;
}

function EvidenceChannel({ channel }) {
  return <section className="evidence-channel" data-scope={channel.scope}><h2>{channel.label}</h2><ScopeNote scopeLabel={channel.scopeLabel} sourcePath={channel.sourcePath} qualification={channel.qualification} /><ChannelState state={channel.state} />{channel.state.state === "available" ? <JsonValue value={channel.payload} /> : null}</section>;
}

function lineageIdentity(projection) {
  const identity = projection?.identity;
  if (!identity || typeof identity !== "object") return null;
  const required = ["resultId", "analysisWindowId", "sourceRunId", "connectionId", "systemId", "observationLineageDigest"];
  if (required.some((key) => !String(identity[key] ?? "").trim())) return null;
  const observationCount = Number(identity.observationCount);
  if (!Number.isInteger(observationCount) || observationCount < 0 || observationCount > 5000) return null;
  return { ...identity, observationCount };
}

function CanonicalObservationLineage({ projection, apiFetch }) {
  const identity = useMemo(() => lineageIdentity(projection), [projection]);
  const [state, setState] = useState({ key: identity ? "loading" : "not-canonical", records: [] });

  useEffect(() => {
    if (!identity || typeof apiFetch !== "function") {
      setState({ key: "not-canonical", records: [] });
      return undefined;
    }
    let cancelled = false;
    const controller = new AbortController();
    setState({ key: "loading", records: [] });
    (async () => {
      const records = [];
      const cursors = new Set();
      const observationIds = new Set();
      const pageLimit = Math.max(identity.observationCount, 1);
      let cursor = null;
      do {
        const page = await getTelemetryAnalysisResultLineage({
          apiFetch,
          connectionId: identity.connectionId,
          runId: identity.sourceRunId,
          systemId: identity.systemId,
          resultId: identity.resultId,
          assetId: identity.assetId,
          limit: pageLimit,
          cursor,
          signal: controller.signal,
        });
        if (
          String(page?.result_id ?? "") !== String(identity.resultId)
          || String(page?.analysis_window_id ?? "") !== String(identity.analysisWindowId)
          || String(page?.observation_lineage_digest ?? "") !== String(identity.observationLineageDigest)
          || Number(page?.observation_count) !== identity.observationCount
          || page?.lineage_verified !== true
          || !Array.isArray(page?.records)
          || page.records.length > pageLimit
        ) throw new Error("canonical_lineage_identity_mismatch");
        for (const record of page.records) {
          const observationId = String(record?.observation_id ?? "");
          const expectedAsset = identity.assetId == null || identity.assetId === "" ? null : String(identity.assetId);
          const actualAsset = record?.asset_id == null || record.asset_id === "" ? null : String(record.asset_id);
          if (
            !observationId
            || observationIds.has(observationId)
            || String(record?.connection_id ?? "") !== String(identity.connectionId)
            || String(record?.system_id ?? "") !== String(identity.systemId)
            || actualAsset !== expectedAsset
          ) throw new Error("canonical_lineage_record_scope_mismatch");
          observationIds.add(observationId);
          records.push(record);
        }
        if (records.length > identity.observationCount) throw new Error("canonical_lineage_count_mismatch");
        const next = page.next_cursor == null ? null : String(page.next_cursor);
        if (next && page.records.length === 0) throw new Error("canonical_lineage_empty_page");
        if (next && cursors.has(next)) throw new Error("canonical_lineage_cursor_repeated");
        if (next) cursors.add(next);
        cursor = next;
      } while (cursor);
      if (records.length !== identity.observationCount) throw new Error("canonical_lineage_count_mismatch");
      if (!cancelled) setState({ key: "ready", records });
    })().catch(() => {
      if (!cancelled && !controller.signal.aborted) setState({ key: "unavailable", records: [] });
    });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [apiFetch, identity]);

  if (!identity) return null;
  return (
    <section className="canonical-observation-lineage" data-state={state.key}>
      <h2>Verified observation lineage</h2>
      {state.key === "loading" ? <p>Loading exact scoped observation lineage…</p> : null}
      {state.key === "unavailable" ? <p className="case-unavailable">Exact canonical observation lineage is unavailable for this scoped result.</p> : null}
      {state.key === "ready" ? <><p>{state.records.length} observations verified against <code>{identity.observationLineageDigest}</code>.</p><JsonValue value={state.records} /></> : null}
    </section>
  );
}

export function EvidenceRecordWorkspace({ projection, apiFetch, onTrace, onBack }) {
  if (!projection || projection.variant === "unavailable") return <ProjectionUnavailable projection={projection} onBack={onBack} />;
  const linkedPackage = projection.package.scope === "finding";
  const analysisScoped = projection.identity?.scope === "analysis";
  const dashboardSummary = projectEvidenceDashboardSummary(projection);
  const identityRows = Object.entries(projection.identity).filter(([key]) => key !== "findingKey");
  const engineRows = Object.entries(projection.engine).filter(([, value]) => value !== null);
  return (
    <div className="case-workspace evidence-record-workspace" data-testid="evidence-record">
      <button type="button" className="evidence-back" onClick={onBack}>Back to investigation</button>
      <EvidenceDashboard summary={dashboardSummary} variant={projection.variant} />
      <details className="evidence-record-technical" open={!dashboardSummary}>
        <summary>Technical evidence and audit trail</summary>
        <div className="evidence-record-technical__body">
      {analysisScoped ? <CaseHeader eyebrow="Evidence record" header={projection.header} /> : null}
      <p className="evidence-record-intro">{analysisScoped ? "Complete analysis identity, provenance, and available run-scoped technical channels from the persisted connector result." : "Complete finding evidence and explicitly labeled supporting analysis context. Analysis-run and system-scoped channels are not finding provenance."}</p>
      <ProjectionQualification qualification={projection.projectionQualification} depth="evidence" />
      <div className="evidence-record-grid evidence-record-grid--audit">
        <section><h2>Record identity</h2><dl className="classification-detail-grid">{identityRows.map(([key, value]) => <div key={key}><dt>{displayLabel(key)}</dt><dd>{value ?? "Not supplied"}</dd></div>)}</dl></section>
        <section><h2>Recorded times</h2><dl className="classification-detail-grid"><div><dt>Generated</dt><dd>{projection.timestamps.generatedAt ?? "Not supplied"}</dd></div><div><dt>First detected</dt><dd>{projection.timestamps.firstDetectedAt ?? "Not supplied"}</dd></div></dl><RecordList items={projection.timestamps.sourceRanges} empty="No source time ranges were recorded." /></section>
        <section><h2>Signals</h2>{projection.signals.length ? <dl className="classification-detail-grid">{projection.signals.map((signal) => <div key={signal.rawId || signal.display}><dt>{signal.display}</dt><dd><code>{signal.rawId || "Raw ID not supplied"}</code><br />Canonical: <code>{signal.canonicalId || "Not supplied"}</code></dd></div>)}</dl> : <p className="case-unavailable">No finding-scoped signal identity was recorded.</p>}</section>
        <section><h2>{analysisScoped ? "Analysis relationships" : "Finding-owned relationships"}</h2><RecordList items={projection.exactRelationships} empty={analysisScoped ? "No result-level relationship record was supplied at this depth." : "No finding-owned relationship record was supplied."} /></section>
        <section><h2>Supporting evidence</h2><RecordList items={projection.supportingEvidence.statements} empty={analysisScoped ? "No separate result-level supporting statements were supplied." : "No finding-owned supporting statements were supplied."} /><h3>Evidence items</h3><RecordList items={projection.supportingEvidence.items} empty={analysisScoped ? "No separate result-level evidence items were supplied." : "No structured finding evidence items were supplied."} /></section>
      </div>
      <section className={`evidence-package-association evidence-package-association--${projection.package.scope}`}>
        <h2>{linkedPackage ? "Package explicitly linked to this finding" : projection.package.scope === "run" ? "Related package for this analysis run" : projection.package.scope === "related" ? "Related evidence package" : "Evidence package unavailable"}</h2>
        <ScopeNote scopeLabel={projection.package.scopeLabel} sourcePath={projection.package.sourcePath} />
        {projection.package.packageId ? <p>Package ID <code>{projection.package.packageId}</code></p> : null}
        {projection.package.immutableDetails ? <JsonValue value={projection.package.immutableDetails} /> : null}
      </section>
      {linkedPackage ? <RelatedEvidencePackages packageId={projection.package.packageId} apiFetch={apiFetch} /> : null}
      <div className="evidence-channel-grid">{projection.channels.map((channel) => <EvidenceChannel key={`${channel.key}-${channel.sourcePath}`} channel={channel} />)}</div>
      <div className="evidence-record-grid evidence-record-grid--audit">
        <section><h2>Classification</h2><JsonValue value={projection.classifications.classification} /><h3>Confidence contract</h3><JsonValue value={projection.classifications.confidenceContract} /><h3>Alternative explanations</h3><RecordList items={projection.classifications.alternatives} empty="No alternative explanations were recorded." /></section>
        <section><h2>Evidence sufficiency</h2><p>{projection.sufficiency.status || "Unavailable"}</p><RecordList items={projection.sufficiency.reasons} empty="No additional sufficiency reasons were recorded." /></section>
        <section><h2>Limitations</h2><h3>Material</h3><RecordList items={projection.limitations.material} empty="None recorded." /><h3>Technical</h3><RecordList items={projection.limitations.technical} empty="None recorded." /><h3>Contradictions</h3><RecordList items={projection.limitations.contradictions} empty="None recorded." /></section>
        <section><h2>Finding provenance and lineage</h2><JsonValue value={projection.lineage} /></section>
        <CanonicalObservationLineage projection={projection} apiFetch={apiFetch} />
        <section><h2>Engine and build</h2>{engineRows.length ? <dl className="classification-detail-grid">{engineRows.map(([key, value]) => <div key={key}><dt>{displayLabel(key)}</dt><dd>{value}</dd></div>)}</dl> : <p className="case-unavailable">Engine metadata was not supplied.</p>}</section>
        <section><h2>Audit history</h2><JsonValue value={projection.audit} /></section>
      </div>
      <section className="evidence-record-actions"><div>{projection.actions.exportScopeLabel ? <p className="evidence-scope-note"><strong>{projection.actions.exportScopeLabel}</strong></p> : null}<EvidencePackageExport runId={projection.actions.exportRunId} apiFetch={apiFetch} disabled={!projection.actions.exportRunId} /></div>{projection.actions.traceRoute ? <button type="button" className="forensic-button forensic-button--secondary" onClick={onTrace}>Open trace mode</button> : null}</section>
        </div>
      </details>
    </div>
  );
}
