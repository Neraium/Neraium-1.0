import { EmptyState, MetricGrid, Panel } from "./workspacePrimitives";

const CHANGELOG_ENTRIES = [
  {
    date: "2026-07-16",
    title: "Product language standardized",
    detail: "Neraium now names the platform separately from Systemic Infrastructure Intelligence and uses consistent operator-facing terms across every workspace.",
  },
  {
    date: "2026-07-16",
    title: "Datasets and connectors separated",
    detail: "Dataset imports, connector setup, and connector health now have distinct labels and status messages.",
  },
  {
    date: "2026-07-16",
    title: "Insight review clarified",
    detail: "Insights, evidence, severity, and facility state now use consistent labels and explain the next operator action.",
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
    ["Service address", `${displayValue(diagnostics.api?.backend_host)}:${displayValue(diagnostics.api?.backend_port)}`],
    ["Dataset import endpoint", displayValue(diagnostics.api?.upload_endpoint)],
    ["Release", displayValue(diagnostics.deployment?.build_sha)],
    ["Deployment environment", displayValue(diagnostics.deployment?.app_env)],
    ["Service role", displayValue(diagnostics.deployment?.process_role)],
    ["Analysis status", displayValue(diagnostics.upload?.upload_state_backend)],
    ["Queued analyses", displayValue(diagnostics.upload?.queue_backend)],
    ["Shared analysis storage", displayValue(diagnostics.upload?.upload_state_shared_configured)],
    ["Background analysis service", displayValue(diagnostics.worker?.startup_worker_started || diagnostics.worker?.configured_start_background_workers)],
    ["Latest analysis identifier", displayValue(diagnostics.upload?.latest_upload_session_id)],
    ["Latest analysis status", displayValue(diagnostics.upload?.latest_upload_status || diagnostics.upload?.latest_upload_state)],
    ["Latest service message", displayValue(diagnostics.upload?.latest_upload_error_type || diagnostics.upload?.latest_upload_message)],
  ];
}

export default function HelpChangelogWorkspace({
  apiStatus = null,
  onWorkspaceNavigate = null,
}) {
  const diagnostics = apiStatus?.diagnostics ?? null;
  const rows = diagnosticsRows(diagnostics);
  const warnings = Array.isArray(diagnostics?.warnings) ? diagnostics.warnings : [];
  return (
    <section className="workspace-surface help-changelog">
      <div className="observation-center__hero">
        <section className="observation-center__summary help-changelog__hero" aria-label="Platform guide and service status">
          <p className="section-token">Help & Status</p>
          <h1>Platform Guide & Service Status</h1>
          <p>
            Neraium is the platform. Systemic Infrastructure Intelligence (SII) analyzes infrastructure behavior and presents operator-reviewable insights with evidence. Neraium remains read-only.
          </p>
          <MetricGrid
            metrics={[
              { label: "Control boundary", value: "Read-only" },
              { label: "Sharing", value: "Operator-controlled" },
              { label: "Insight priority", value: "Severity labels" },
              { label: "Intelligence", value: "SII" },
            ]}
            compact
          />
          <div className="intake-flow__controls">
            <button type="button" className="secondary-command-button" onClick={() => onWorkspaceNavigate?.("observation-center")}>
              Open Insights
            </button>
          </div>
        </section>
      </div>

      <div className="workspace-grid workspace-grid--console observation-center__grid">
        <Panel title="Product terminology" className="span-7 observation-center__panel">
          <ul className="compact-list">
            <li><strong>System:</strong> equipment or processes grouped by shared telemetry behavior.</li>
            <li><strong>Dataset:</strong> a bounded collection of timestamped telemetry imported for analysis.</li>
            <li><strong>Connector:</strong> a configured read-only integration to a telemetry source.</li>
            <li><strong>Analysis:</strong> one execution of SII against a dataset.</li>
            <li><strong>Insight:</strong> an operational change that may warrant investigation.</li>
            <li><strong>Evidence:</strong> observed measurements and relationships supporting an insight.</li>
          </ul>
        </Panel>

        <Panel title="Status meanings" className="span-5 observation-center__panel">
          <ul className="compact-list">
            <li><strong>Insight severity:</strong> Critical, High, Moderate, or Low investigation priority.</li>
            <li><strong>Connector health:</strong> Healthy, Degraded, Offline, or Not configured.</li>
            <li><strong>Facility state:</strong> Stable, Investigation recommended, Urgent investigation, Baseline needed, or Analyzing.</li>
            <li>Evidence supports an interpretation but does not prove root cause.</li>
          </ul>
        </Panel>

        <Panel title="Service diagnostics" className="span-12 observation-center__panel">
          {rows.length === 0 ? (
            <EmptyState title="Service diagnostics unavailable" body="Refresh the Command Center to run another health check. If diagnostics remain unavailable, contact an administrator." compact />
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
                  <strong>Service warnings</strong>
                  <p>{warnings.join(", ")}</p>
                </div>
              ) : null}
            </>
          )}
        </Panel>

        <Panel title="Product updates" className="span-12 observation-center__panel">
          {CHANGELOG_ENTRIES.length === 0 ? (
            <EmptyState title="No product updates" body="Product update notes will appear here after a release." compact />
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
