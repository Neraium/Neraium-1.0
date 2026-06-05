import { EmptyState, MetricGrid, Panel } from "./workspacePrimitives";

const CHANGELOG_ENTRIES = [
  {
    date: "2026-06-05",
    title: "Historical fact moved into the evidence model",
    detail: "Observation exports and API responses now carry the corpus-derived historical fact instead of rebuilding it in the frontend.",
  },
  {
    date: "2026-06-05",
    title: "Observation review simplified",
    detail: "Trust boundaries and version history now live in a dedicated help workspace so observation review stays focused on evidence.",
  },
  {
    date: "2026-06-04",
    title: "Instrument language tightened",
    detail: "Warm shift tones replaced emergency red so the instrument stays calm while still showing sustained deformation.",
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
          Back to Gate
        </button>
        <button type="button" className="system-gate__settings-action" onClick={() => onWorkspaceNavigate?.("observation-center")}>
          Open Observation Center
        </button>
      </div>

      <div className="observation-center__hero">
        <section className="observation-center__summary help-changelog__hero" aria-label="Help and changelog summary">
          <p className="section-token">Trust Boundary</p>
          <h1>Help / Changelog</h1>
          <p>
            Neraium observes structural change, records evidence, and stays read-only. This page holds the operating boundary and the version history so observation review can stay quiet.
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
        <Panel title="What the instrument does" className="span-7 observation-center__panel">
          <ul className="compact-list">
            <li>Ingests multivariate telemetry without requiring domain semantics.</li>
            <li>Learns a baseline structural regime and watches for persistent deformation.</li>
            <li>Surfaces observations as relational facts, not instructions.</li>
            <li>Records operator feedback as evidence for future investigations.</li>
          </ul>
        </Panel>

        <Panel title="What it does not do" className="span-5 observation-center__panel">
          <ul className="compact-list">
            <li>No actuation or setpoint control.</li>
            <li>No severity score, risk rating, or prediction.</li>
            <li>No root cause analysis.</li>
            <li>No hidden cross-site sharing unless the operator exports evidence.</li>
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
