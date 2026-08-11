import React, { useEffect, useRef } from "react";
import ConfidenceTierChip from "./ConfidenceTierChip";
import DataGapBand from "./DataGapBand";
import EvidenceLineage from "./EvidenceLineage";
import ReadOnlyIndicator from "./ReadOnlyIndicator";

function evidenceValue(value, fallback = "Unavailable") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function EvidenceRecordContext({ record }) {
  if (!record || typeof record !== "object" || Object.keys(record).length === 0) return null;
  const timestamps = record.timestamps && typeof record.timestamps === "object" ? record.timestamps : {};
  return (
    <section className="evidence-drawer__record">
      <h3>Evidence record</h3>
      <dl>
        <div><dt>Evidence run</dt><dd>{evidenceValue(record.run_id ?? record.job_id)}</dd></div>
        <div><dt>Source</dt><dd>{evidenceValue(record.source_name)}</dd></div>
        <div><dt>Window start</dt><dd>{evidenceValue(timestamps.upload_start)}</dd></div>
        <div><dt>Window end</dt><dd>{evidenceValue(timestamps.upload_end)}</dd></div>
        <div><dt>Rows accepted</dt><dd>{evidenceValue(record.rows_accepted)}</dd></div>
        <div><dt>Evidence hash</dt><dd>{evidenceValue(record.evidence_hash)}</dd></div>
        {record.finding_id ? <div><dt>Finding identity</dt><dd>{record.finding_id}</dd></div> : null}
        {record.system_id ? <div><dt>System identity</dt><dd>{record.system_id}</dd></div> : null}
      </dl>
    </section>
  );
}

export default function EvidenceDrawer({ open, finding, relationship, result, record = null, strictMissingValues = false, gaps = [], onClose, onTrace }) {
  const closeRef = useRef(null);
  useEffect(() => {
    if (open) closeRef.current?.focus();
  }, [open]);
  if (!open || !finding) return null;
  return (
    <aside className="evidence-drawer" role="dialog" aria-modal="false" aria-labelledby="evidence-drawer-title">
      <div className="evidence-drawer__handle" aria-hidden="true" />
      <header><div><span className="forensic-kicker">Evidence drawer</span><h2 id="evidence-drawer-title">{relationship?.label || finding.title}</h2></div><button ref={closeRef} type="button" className="forensic-icon-button" aria-label="Close evidence drawer" onClick={onClose}>×</button></header>
      <ReadOnlyIndicator compact />
      <section className="evidence-drawer__confidence"><span>Confidence state</span>{finding.tier || !strictMissingValues ? <ConfidenceTierChip tier={finding.tier} showDefinition /> : <strong>Unavailable</strong>}</section>
      <EvidenceLineage finding={finding} relationship={relationship} result={result} omitUnavailable={strictMissingValues} />
      <section className="evidence-drawer__split"><div><h3>Supporting evidence</h3>{finding.supporting.length ? <ul>{finding.supporting.map((item) => <li key={item}>{item}</li>)}</ul> : <p>None supplied.</p>}</div><div><h3>Contradicting evidence</h3>{finding.contradictions.length ? <ul>{finding.contradictions.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No contradiction was supplied.</p>}</div></section>
      <section><h3>Limitations</h3>{finding.limitations.length ? <ul>{finding.limitations.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No material limitation was supplied with this result.</p>}</section>
      <EvidenceRecordContext record={record} />
      {gaps.map((gap) => <DataGapBand key={gap.id} gap={gap} />)}
      <footer>{onTrace ? <button type="button" className="forensic-button" onClick={onTrace}>Open trace mode</button> : null}</footer>
    </aside>
  );
}
