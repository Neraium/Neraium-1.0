import { EmptyState, MetricGrid, Panel } from "./workspacePrimitives";

const CHANGELOG_ENTRIES = [
  {
    date: "2026-06-05",
    title: "Historical fact moved into the evidence model",
    detail: "Observation exports and API responses now carry the corpus-derived historical fact instead of rebuilding it in the frontend.",
  },
  {
    date: "2026-06-05",
    title: "Issues simplified",
    detail: "Trust boundaries and version history now live in a dedicated help workspace so issues stay focused on what changed.",
  },
  {
    date: "2026-06-04",
    title: "Instrument language tightened",
    detail: "Warm shift tones replaced emergency red so the instrument stays calm while still showing sustained change.",
  },
];

export default function HelpChangelogWorkspace({
  onBackToGate = null,
  onWorkspaceNavigate = null,
}) {
  return (
    <section className="workspace-surface help-changelog">
      <div className="observation-center__back-control">
        <button type="button" className="system-gate__settings-action" onClick={() => onBackToGate?.()}>
          Back to Health
        </button>
        <button type="button" className="system-gate__settings-action" onClick={() => onWorkspaceNavigate?.("observation-center")}>
          Open Issues
        </button>
      </div>

      <div className="observation-center__hero">
        <section className="observation-center__summary help-changelog__hero" aria-label="Help and changelog summary">
          <p className="section-token">Technical</p>
          <h1>Technical</h1>
          <p>
            Neraium observes operating pattern changes, records support details, and stays read-only. This page holds the operating boundary and version history so issues stay focused.
          </p>
          <MetricGrid
            metrics={[
              { label: "Control boundary", value: "Read-only" },
              { label: "Sharing", value: "Operator-controlled" },
              { label: "Review posture", value: "Quiet" },
              { label: "Versioning", value: "Plain language" },
            ]}
            compact
          />
        </section>
      </div>

      <div className="workspace-grid workspace-grid--console observation-center__grid">
        <Panel title="What Neraium does" className="span-7 observation-center__panel">
          <ul className="compact-list">
            <li>Ingests multivariate telemetry without requiring domain semantics.</li>
            <li>Compares current telemetry with historical operating patterns.</li>
            <li>Surfaces issues as operating changes, not control instructions.</li>
            <li>Records engineer feedback for future comparisons.</li>
          </ul>
        </Panel>

        <Panel title="What it does not do" className="span-5 observation-center__panel">
          <ul className="compact-list">
            <li>No actuation or setpoint control.</li>
            <li>No severity score, risk rating, or prediction.</li>
            <li>No automatic root-cause claim.</li>
            <li>No hidden cross-site sharing unless the operator exports records.</li>
          </ul>
        </Panel>

        <Panel title="Version history" className="span-12 observation-center__panel">
          {CHANGELOG_ENTRIES.length === 0 ? (
            <EmptyState title="No changelog entries" body="No version notes are available yet." compact />
          ) : (
            <ul className="compact-list">
              {CHANGELOG_ENTRIES.map((entry) => (
                <li key={`${entry.date}-${entry.title}`}>
                  <strong>{entry.date} - {entry.title}</strong>
                  <div>{entry.detail}</div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </section>
  );
}
