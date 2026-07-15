const AVAILABLE_SOURCES = [
  {
    icon: "CSV",
    label: "Historical CSV",
    detail: "Use exported telemetry when live telemetry is unavailable.",
    status: "Available Source",
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
      ? { label: "Historical dataset imported", tone: "ready", statusKey: "ready" }
      : { label: "Live connector unavailable", tone: "unknown", statusKey: "waiting" };

  return (
    <div className="operational-grid operational-grid--data-sources">
      <section className="operational-panel operational-panel--wide data-source-status-panel" aria-label="Telemetry Sources">
        <PanelHeader
          eyebrow="Source Health"
          title="Telemetry Sources"
          subtitle="Monitor source availability and last successful import or synchronization."
        />
        <StatusBadge label={sourceHealth.label} tone={sourceHealth.tone} statusKey={sourceHealth.statusKey} />
        <DetailGrid rows={model.dataSourceRows} />
      </section>

      <section className="operational-panel operational-panel--wide data-source-actions-panel" aria-label="Primary Action">
        <PanelHeader eyebrow="Primary Action" title="Analyze Dataset" subtitle="Upload historical telemetry and create or refresh the behavioral baseline." />
        <div className="data-source-action-grid data-source-action-grid--single">
          <button type="button" className="command-button data-source-action data-source-action--primary" onClick={onAnalyzeHistoricalData} disabled={model.analyzeDisabled}>
            <strong>Analyze Dataset</strong>
            <span>Upload historical telemetry and create or refresh the behavioral baseline.</span>
          </button>
        </div>
      </section>

      <section className="operational-panel" aria-label="Available Sources">
        <PanelHeader eyebrow="Available Source" title="Historical CSV" subtitle="Use exported telemetry when live telemetry is unavailable." />
        <div className="telemetry-source-grid telemetry-source-grid--compact">
          {AVAILABLE_SOURCES.map((source) => (
            <ConnectorCard key={source.label} {...source} available />
          ))}
        </div>
      </section>

      <section className="operational-panel" aria-label="Planned Connectors">
        <PanelHeader eyebrow="Planned Connectors" title="Connector Roadmap" subtitle="Read-only integrations planned for live telemetry intake." />
        <div className="telemetry-source-grid telemetry-source-grid--compact">
          {PLANNED_CONNECTORS.map((source) => (
            <ConnectorCard key={source.label} {...source} status="Planned" />
          ))}
        </div>
      </section>

      <section className="operational-panel read-only-architecture" aria-label="Read-Only Architecture">
        <PanelHeader eyebrow="Read-Only Architecture" title="Read-Only Architecture" subtitle="" />
        <p>Neraium never writes to:</p>
        <ul className="compact-list compact-list--safety">
          <li>PLCs</li>
          <li>SCADA</li>
          <li>BMS</li>
          <li>Equipment Controllers</li>
        </ul>
        <strong>Telemetry is always read-only.</strong>
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
