import React from "react";

export default function TraceTimeline({ steps = [], selectedId = null, onSelect }) {
  return (
    <ol className="trace-timeline" aria-label="Computational lineage">
      {steps.map((step, index) => <li key={step.id} className={selectedId === step.id ? "is-selected" : ""}>
        <button type="button" onClick={() => onSelect?.(step)} aria-pressed={selectedId === step.id}>
          <span className="trace-timeline__index">{String(index + 1).padStart(2, "0")}</span>
          <span className="trace-timeline__body"><span className="forensic-kicker">{step.type}</span><strong>{step.output}</strong><small>{step.transformation}</small></span>
          <span className="trace-timeline__meta"><time>{step.timestamp || "Timestamp not supplied"}</time><span>{step.classification}</span></span>
        </button>
        {selectedId === step.id ? <dl className="trace-timeline__details">
          <div><dt>Source</dt><dd>{step.source}</dd></div><div><dt>Transformation</dt><dd>{step.transformation}</dd></div><div><dt>Input</dt><dd>{step.input}</dd></div><div><dt>Output</dt><dd>{step.output}</dd></div><div><dt>Version / model</dt><dd>{step.version}</dd></div><div><dt>Evidence classification</dt><dd>{step.classification}</dd></div><div><dt>Governance boundary</dt><dd>{step.governance}</dd></div><div><dt>Confidence contribution</dt><dd>{step.confidenceContribution}</dd></div>
        </dl> : null}
      </li>)}
    </ol>
  );
}
