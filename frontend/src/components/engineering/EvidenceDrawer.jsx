import React, { useEffect, useRef } from "react";
import ConfidenceTierChip from "./ConfidenceTierChip";
import DataGapBand from "./DataGapBand";
import EvidenceLineage from "./EvidenceLineage";
import ReadOnlyIndicator from "./ReadOnlyIndicator";

export default function EvidenceDrawer({ open, finding, relationship, result, gaps = [], onClose, onTrace }) {
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
      <section className="evidence-drawer__confidence"><span>Confidence state</span><ConfidenceTierChip tier={finding.tier} showDefinition /></section>
      <EvidenceLineage finding={finding} relationship={relationship} result={result} />
      <section className="evidence-drawer__split"><div><h3>Supporting evidence</h3>{finding.supporting.length ? <ul>{finding.supporting.map((item) => <li key={item}>{item}</li>)}</ul> : <p>None supplied.</p>}</div><div><h3>Contradicting evidence</h3>{finding.contradictions.length ? <ul>{finding.contradictions.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No contradiction was supplied.</p>}</div></section>
      <section><h3>Limitations</h3>{finding.limitations.length ? <ul>{finding.limitations.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No material limitation was supplied with this result.</p>}</section>
      {gaps.map((gap) => <DataGapBand key={gap.id} gap={gap} />)}
      <footer>{onTrace ? <button type="button" className="forensic-button" onClick={onTrace}>Open trace mode</button> : null}</footer>
    </aside>
  );
}
