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

function displayValue(value) {
  if (value === true) return "Yes";
  if (value === false) return "No";
  if (value === null || value === undefined || value === "") return "Unknown";
  return String(value);
}

function diagnosticsRows(diagnostics) {
  if (!diagnostics) return [];
  return [
    ["API host", `${displayValue(diagnostics.api?.backend_host)}:${displayValue(diagnostics.api?.backend_port)}`],
    ["Upload route", displayValue(diagnostics.api?.upload_endpoint)],
    ["Build", displayValue(diagnostics.deployment?.build_sha)],
    ["Environment", displayValue(diagnostics.deployment?.app_env)],
    ["Process role", displayValue(diagnostics.deployment?.process_role)],
    ["Upload state", displayValue(diagnostics.upload?.upload_state_backend)],
    ["Queue", displayValue(diagnostics.upload?.queue_backend)],
    ["Shared state", displayValue(diagnostics.upload?.upload_state_shared_configured)],
    ["Worker", displayValue(diagnostics.worker?.startup_worker_started || diagnostics.worker?.configured_start_background_workers)],
    ["Latest upload", displayValue(diagnostics.upload?.latest_upload_session_id)],
    ["Latest status", displayValue(diagnostics.upload?.latest_upload_status || diagnostics.upload?.latest_upload_state)],
    ["Latest error", displayValue(diagnostics.upload?.latest_upload_error_type || diagnostics.upload?.latest_upload_message)],
  ];
}

export default function HelpChangelogWorkspace({
  apiStatus = null,
  onBackToGate = null,
  onWorkspaceNavigate = null,
}) {
  const diagnostics = apiStatus?.diagnostics ?? null;
  const rows = diagnosticsRows(diagnostics);
  const warnings = Array.isArray(diagnostics?.warnings) ? diagnostics.warnings : [];
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

        <Panel title="Production diagnostics" className="span-12 observation-center__panel">
          {rows.length === 0 ? (
            <EmptyState title="Diagnostics unavailable" body="Backend diagnostics will appear after the next health check." compact />
          ) : (
            <>
              <ul className="compact-list" data-testid="production-diagnostics">
                {rows.map(([label, value]) => (
                  <li key={label}>
                    <span className="metadata-text">{label}</span>
                    <strong>{value}</strong>
                  </li>
                ))}
              </ul>
              {warnings.length > 0 ? (
                <div className="upload-partial-alert" role="status">
                  <strong>Deployment warnings</strong>
                  <p>{warnings.join(", ")}</p>
                </div>
              ) : null}
            </>
          )}
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
