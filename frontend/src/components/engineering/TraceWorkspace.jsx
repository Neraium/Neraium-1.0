import React, { useState } from "react";
import EvidencePackageExport from "./EvidencePackageExport";
import TraceTimeline from "./TraceTimeline";

export default function TraceWorkspace({ model, finding, apiFetch, onBack }) {
  const [selectedId, setSelectedId] = useState(model.trace[0]?.id ?? null);
  const runId = finding?.runId ?? model?.result?.run_id ?? model?.result?.job_id ?? model?.result?.upload_id ?? null;
  return (
    <div className="trace-workspace">
      <button type="button" className="evidence-back" onClick={onBack}>Back to evidence</button>
      <header className="forensic-page-header"><div><span className="forensic-kicker">Technical details</span><h1>Trace mode</h1></div></header>
      <div className="trace-actions"><EvidencePackageExport runId={runId} apiFetch={apiFetch} /></div>
      <TraceTimeline steps={model.trace} selectedId={selectedId} onSelect={(step) => setSelectedId(step.id)} />
    </div>
  );
}
