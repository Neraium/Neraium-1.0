const AVAILABLE_SOURCES = [
  {
    icon: "CSV",
    label: "Historical CSV Import",
    detail: "Use exported telemetry when historian access is not connected.",
    status: "Available Today",
  },
  {
    icon: "SII",
    label: "Historical Analysis",
    detail: "Establish or refresh the Operational Fingerprint from available operating records.",
    status: "Available Today",
  },
];

const PLANNED_INTEGRATIONS = [
  { icon: "OPC", label: "OPC-UA", detail: "Industrial tag intake from OPC-UA endpoints." },
  { icon: "MQ", label: "MQTT", detail: "Broker topic subscriptions for live monitoring." },
  { icon: "PI", label: "PI System", detail: "Historian connectivity for operating windows." },
  { icon: "BMS", label: "SCADA / BMS", detail: "Facility supervisory system connectors." },
  { icon: "+", label: "Additional Connectors", detail: "Expanded source coverage for pilot environments." },
];

export default function DataSourcesView({ model, helpers, onAnalyzeHistoricalData, onSelectCsv }) {
  const { DetailGrid, PanelHeader, StatusBadge } = helpers;

  return (
    <div className="operational-grid operational-grid--data-sources">
      <section className="operational-panel operational-panel--wide data-source-status-panel" aria-label="Data Sources">
        <PanelHeader
          eyebrow="Status"
          title="Telemetry Sources"
          subtitle="Connect read-only telemetry sources for Operational Fingerprint review."
        />
        <StatusBadge label={model.dashboardStatus.label} tone={model.dashboardStatus.tone} statusKey={model.dashboardStatus.statusKey} />
      </section>

      <section className="operational-panel operational-panel--wide data-source-actions-panel" aria-label="Primary Actions">
        <PanelHeader eyebrow="Primary Actions" title="Start Analysis" subtitle="CSV import is one source path for establishing operational intelligence." />
        <div className="data-source-action-grid">
          <button type="button" className="command-button data-source-action data-source-action--primary" onClick={onAnalyzeHistoricalData} disabled={model.analyzeDisabled}>
            <strong>Analyze New Dataset</strong>
            <span>Create or refresh the Operational Fingerprint.</span>
          </button>
          <button type="button" className="secondary-command-button data-source-action" onClick={onSelectCsv} disabled={model.analyzeDisabled}>
            <strong>Import Historical CSV</strong>
            <span>Use exported telemetry when no live source is connected.</span>
          </button>
          <button type="button" className="secondary-command-button data-source-action" disabled>
            <strong>Connect Live Telemetry</strong>
            <span>Planned connector workflow.</span>
          </button>
        </div>
      </section>

      <section className="operational-panel" aria-label="Available Sources">
        <PanelHeader eyebrow="Available Sources" title="Available Today" subtitle="" />
        <div className="telemetry-source-grid telemetry-source-grid--compact">
          {AVAILABLE_SOURCES.map((source) => (
            <ConnectorCard key={source.label} {...source} available />
          ))}
        </div>
      </section>

      <section className="operational-panel" aria-label="Planned Integrations">
        <PanelHeader eyebrow="Planned Integrations" title="Connector Roadmap" subtitle="" />
        <div className="telemetry-source-grid telemetry-source-grid--compact">
          {PLANNED_INTEGRATIONS.map((source) => (
            <ConnectorCard key={source.label} {...source} status="Planned" />
          ))}
        </div>
      </section>

      <section className="operational-panel" aria-label="Telemetry Status">
        <PanelHeader eyebrow="Telemetry Status" title="Source State" subtitle="" />
        <DetailGrid rows={model.dataSourceRows} />
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
