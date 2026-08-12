import React, { useState } from "react";

const WORKFLOW = [
  { label: "Import", detail: "Historical data" },
  { label: "Learn", detail: "Normal behavior" },
  { label: "Compare", detail: "Current operation" },
  { label: "Review", detail: "Engineering findings" },
];

function WorkflowSteps() {
  return (
    <ol className="baseline-workflow" aria-label="Neraium baseline workflow">
      {WORKFLOW.map((step, index) => (
        <li key={step.label}>
          <span aria-hidden="true">{index + 1}</span>
          <div><strong>{step.label}</strong><small>{step.detail}</small></div>
        </li>
      ))}
    </ol>
  );
}

export function SupportedFormats({ visible }) {
  if (!visible) return null;
  return (
    <div className="baseline-formats" role="region" aria-label="Supported historical dataset formats">
      <span>CSV</span><span>SCADA CSV</span><span>Historian CSV</span><span>Timestamped telemetry</span>
    </div>
  );
}

function BaselinePreview() {
  return (
    <aside className="baseline-preview" aria-labelledby="baseline-preview-title">
      <header className="baseline-preview__header">
        <div>
          <span>Learning model</span>
          <h2 id="baseline-preview-title">From history to operating context</h2>
        </div>
        <p><span aria-hidden="true" /> Awaiting data</p>
      </header>
      <div className="baseline-preview__field" aria-hidden="true">
        <span className="baseline-preview__core">SII</span>
        <span className="baseline-preview__node baseline-preview__node--a">Signals</span>
        <span className="baseline-preview__node baseline-preview__node--b">Relationships</span>
        <span className="baseline-preview__node baseline-preview__node--c">Patterns</span>
      </div>
      <p className="baseline-preview__note">
        Neraium learns repeatable operating behavior before evaluating change.
      </p>
    </aside>
  );
}

export default function FirstBaselineExperience({ onImport, onExit }) {
  const [formatsVisible, setFormatsVisible] = useState(false);
  return (
    <section className="first-baseline" aria-labelledby="first-baseline-title" data-testid="first-baseline-experience">
      <header className="first-baseline__header">
        <div className="first-baseline__brand"><span aria-hidden="true">N</span><strong>Neraium</strong></div>
        <button type="button" className="baseline-text-button" onClick={onExit}>Go to workspace</button>
      </header>
      <div className="first-baseline__content">
        <div className="first-baseline__intro">
          <p className="forensic-kicker">Welcome</p>
          <h1 id="first-baseline-title">Create Your First Baseline</h1>
          <p>Import a historical dataset. Neraium will learn normal behavior and prepare the engineering workspace.</p>
          <div className="first-baseline__actions">
            <button type="button" className="forensic-button" onClick={onImport}>Import Historical Dataset</button>
            <button
              type="button"
              className="forensic-button forensic-button--secondary"
              aria-expanded={formatsVisible}
              onClick={() => setFormatsVisible((value) => !value)}
            >
              View Supported Formats
            </button>
          </div>
          <SupportedFormats visible={formatsVisible} />
        </div>
        <BaselinePreview />
        <WorkflowSteps />
      </div>
      <footer className="first-baseline__footer">
        <span>Read-only import</span>
        <span>Nothing is changed in your source systems.</span>
      </footer>
    </section>
  );
}

export { WorkflowSteps };
