const AVAILABLE_SOURCES = [
  {
    icon: "CSV",
    label: "CSV dataset import",
    detail: "Import a timestamped telemetry dataset for one SII analysis.",
    status: "Available",
  },
];

const PLANNED_CONNECTORS = [
  { icon: "OPC", label: "OPC UA", detail: "Planned read-only connector for industrial telemetry." },
  { icon: "MQ", label: "MQTT", detail: "Planned read-only connector for broker telemetry." },
  { icon: "BAC", label: "BACnet", detail: "Planned read-only connector for building automation telemetry." },
  { icon: "HIS", label: "Enterprise historians", detail: "Planned read-only connectors for historian telemetry." },
];

export default function DataSourcesView({ model, helpers, onAnalyzeHistoricalData }) {
  const { DetailGrid, PanelHeader, StatusBadge } = helpers;
  const sourceHealth = model.telemetryConnected
    ? { label: "Connector healthy", tone: "active", statusKey: "active" }
    : !["None", "Not connected"].includes(model.sourceLabel)
      ? { label: "Dataset imported", tone: "ready", statusKey: "ready" }
      : { label: "No telemetry data", tone: "unknown", statusKey: "waiting" };
  const findingRows = model.analysisComplete
    ? [
        ["Insights", model.insights.length ? `${model.insights.length} active` : "No active insights"],
        ["Highest severity", model.highestSeverity],
        ["Behavior state", model.behaviorState],
        ["Baseline", model.baselineAvailable ? "Established" : "Pending"],
      ]
    : [
        ["Insights", "Available after analysis"],
        ["Behavior state", "Not analyzed"],
        ["Baseline", "Pending"],
      ];

  return (
    <div className="operational-grid operational-grid--data-sources">
      <section className="operational-panel operational-panel--wide data-source-status-panel" aria-label="Data Availability">
        <PanelHeader
          eyebrow="Telemetry"
          title="Data Availability"
          subtitle="Shows what telemetry is available and the next import action."
        />
        <StatusBadge label={sourceHealth.label} tone={sourceHealth.tone} statusKey={sourceHealth.statusKey} />
        <DetailGrid rows={model.dataSourceRows} />
      </section>

      <section className="operational-panel operational-panel--wide data-source-actions-panel" aria-label="Dataset Analysis">
        <PanelHeader eyebrow="Dataset Analysis" title="Import and Analyze a Dataset" subtitle="Choose a timestamped CSV, validate processing, then return to Command Center." />
        <div className="data-source-action-grid data-source-action-grid--single">
          <button type="button" className="command-button data-source-action data-source-action--primary" onClick={onAnalyzeHistoricalData} disabled={model.analyzeDisabled} title={model.analyzeDisabled ? "Analysis is already in progress. Wait for it to finish before starting another." : "Choose a telemetry CSV to analyze."}>
            <strong>Choose Dataset</strong>
            <span>Run analysis and save evidence.</span>
          </button>
        </div>
      </section>

      <section className="operational-panel" aria-label="Dataset Imports">
        <PanelHeader eyebrow="Datasets" title="Dataset Imports" subtitle="Available now." />
        <div className="telemetry-source-grid telemetry-source-grid--compact">
          {AVAILABLE_SOURCES.map((source) => (
            <ConnectorCard key={source.label} {...source} available />
          ))}
        </div>
      </section>

      <section className="operational-panel" aria-label="Planned Live Connectors">
        <PanelHeader eyebrow="Connectors" title="Planned Live Connectors" subtitle="Not available in this release." />
        <div className="telemetry-source-grid telemetry-source-grid--compact">
          {PLANNED_CONNECTORS.map((source) => (
            <ConnectorCard key={source.label} {...source} status="Planned" />
          ))}
        </div>
      </section>

      <section className="operational-panel" aria-label="Facility Status">
        <PanelHeader eyebrow="Facility Status" title="Facility Status" subtitle="Current operating context." />
        <DetailGrid rows={model.dashboardSummaryRows} />
      </section>

      <section className="operational-panel" aria-label="Analysis Summary">
        <PanelHeader eyebrow="Analysis" title="Analysis Summary" subtitle="Current analysis facts." />
        <DetailGrid rows={findingRows} />
      </section>

      <section className="operational-panel operational-panel--wide read-only-architecture" aria-label="Read-only enforcement">
        <PanelHeader eyebrow="Safety Boundary" title="Read-only Control Boundary" subtitle="Decision support only. No commands or setpoints are written." />
        <ul className="compact-list compact-list--safety">
          <li>PLC commands disabled</li>
          <li>SCADA commands disabled</li>
          <li>BMS commands disabled</li>
          <li>Equipment controller commands disabled</li>
        </ul>
      </section>
    </div>
  );
}

function ConnectorCard({ icon, label, detail, status, available = false }) {
  return (
    <article className={available ? "telemetry-source-card telemetry-source-card--available" : "telemetry-source-card telemetry-source-card--planned"}>
      <div className="telemetry-source-card__header">
        <span className="telemetry-source-card__icon" aria-hidden="true">{icon}</span>
        <small>{status}</small>
      </div>
      <strong>{label}</strong>
      <span>{detail}</span>
    </article>
  );
}
