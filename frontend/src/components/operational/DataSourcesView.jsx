const AVAILABLE_SOURCES = [
  {
    icon: "CSV",
    label: "Historical CSV",
    detail: "Use exported telemetry when live telemetry is unavailable.",
    status: "Available",
  },
];

const PLANNED_CONNECTORS = [
  { icon: "OPC", label: "OPC-UA", detail: "Read-only industrial tag intake from OPC-UA endpoints." },
  { icon: "MQ", label: "MQTT", detail: "Read-only broker topic subscriptions for live monitoring." },
  { icon: "BAC", label: "BACnet", detail: "Read-only building automation telemetry discovery." },
  { icon: "HIS", label: "Historian integrations", detail: "Read-only operating windows from enterprise historians." },
];

export default function DataSourcesView({ model, helpers, onAnalyzeHistoricalData }) {
  const { DetailGrid, PanelHeader, StatusBadge } = helpers;
  const sourceHealth = model.telemetryConnected
    ? { label: "Source healthy", tone: "active", statusKey: "active" }
    : model.sourceLabel !== "None"
      ? { label: "Historical telemetry available", tone: "ready", statusKey: "ready" }
      : { label: "Awaiting telemetry", tone: "unknown", statusKey: "waiting" };
  const findingRows = model.analysisComplete
    ? [
        ["Findings", model.insights.length ? `${model.insights.length} active` : "No active findings"],
        ["Highest severity", model.highestSeverity],
        ["Behavior state", model.behaviorState],
        ["Baseline", model.baselineAvailable ? "Established" : "Pending"],
      ]
    : [
        ["Findings", "Pending baseline"],
        ["Behavior state", "Not analyzed"],
        ["Baseline", "Pending"],
      ];

  return (
    <div className="operational-grid operational-grid--data-sources">
      <section className="operational-panel operational-panel--wide data-source-status-panel" aria-label="Telemetry Sources">
        <PanelHeader
          eyebrow="Telemetry Sources"
          title="Telemetry Sources"
          subtitle="Current source availability and the latest historical or live telemetry used by the platform."
        />
        <StatusBadge label={sourceHealth.label} tone={sourceHealth.tone} statusKey={sourceHealth.statusKey} />
        <DetailGrid rows={model.dataSourceRows} />
      </section>

      <section className="operational-panel operational-panel--wide data-source-actions-panel" aria-label="Primary Analysis Actions">
        <PanelHeader eyebrow="Primary Analysis Actions" title="Analyze Historical Telemetry" subtitle="One canonical workflow uploads historical telemetry and establishes or refreshes the behavioral baseline." />
        <div className="data-source-action-grid data-source-action-grid--single">
          <button type="button" className="command-button data-source-action data-source-action--primary" onClick={onAnalyzeHistoricalData} disabled={model.analyzeDisabled}>
            <strong>Analyze Historical Telemetry</strong>
            <span>Upload telemetry evidence, infer relationships, organize behavior, and persist the behavioral baseline.</span>
          </button>
        </div>
      </section>

      <section className="operational-panel" aria-label="Available Sources">
        <PanelHeader eyebrow="Available Sources" title="Available Sources" subtitle="Supported telemetry sources for the canonical analysis workflow." />
        <div className="telemetry-source-grid telemetry-source-grid--compact">
          {AVAILABLE_SOURCES.map((source) => (
            <ConnectorCard key={source.label} {...source} available />
          ))}
        </div>
      </section>

      <section className="operational-panel" aria-label="Connector Roadmap">
        <PanelHeader eyebrow="Connector Roadmap" title="Connector Roadmap" subtitle="Planned read-only integrations for live telemetry intake." />
        <div className="telemetry-source-grid telemetry-source-grid--compact">
          {PLANNED_CONNECTORS.map((source) => (
            <ConnectorCard key={source.label} {...source} status="Planned" />
          ))}
        </div>
      </section>

      <section className="operational-panel" aria-label="Facility Status">
        <PanelHeader eyebrow="Facility Status" title="Facility Status" subtitle="Read-only facility state used by the Command Center." />
        <DetailGrid rows={model.dashboardSummaryRows} />
      </section>

      <section className="operational-panel" aria-label="Analytical Findings">
        <PanelHeader eyebrow="Analytical Findings" title="Analytical Findings" subtitle="Current finding summary derived from the established behavioral baseline." />
        <DetailGrid rows={findingRows} />
      </section>

      <section className="operational-panel operational-panel--wide read-only-architecture" aria-label="Read-only enforcement">
        <PanelHeader eyebrow="Read-only Enforcement" title="Read-only Enforcement" subtitle="Neraium supports decision-making without controlling facility equipment." />
        <ul className="compact-list compact-list--safety">
          <li>PLC writeback disabled</li>
          <li>SCADA writeback disabled</li>
          <li>BMS writeback disabled</li>
          <li>Equipment controller writeback disabled</li>
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
