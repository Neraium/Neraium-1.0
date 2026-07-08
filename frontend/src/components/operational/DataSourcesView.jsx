export default function DataSourcesView({ model, helpers, onAnalyzeHistoricalData, onSelectCsv }) {
  const { DetailGrid, PanelHeader } = helpers;
  return (
    <div className="operational-grid operational-grid--command-center">
      <section className="operational-panel operational-panel--wide" aria-label="Data Sources">
        <PanelHeader eyebrow="Data Sources" title="Telemetry Sources" subtitle="Read-only telemetry intake. Neraium does not write back to SCADA, PLCs, BMS, controls, or equipment." />
        <div className="telemetry-source-grid telemetry-source-grid--full">
          <SourceCard label="Analyze Historical Data" detail="Analyze exported historical telemetry to establish or refresh the Operational Fingerprint." status="Available now" available onClick={onAnalyzeHistoricalData} />
          <SourceCard label="CSV Import" detail="Use the existing CSV telemetry import and analysis flow." status="Available now" available onClick={onSelectCsv} />
          <SourceCard label="Connect Live Telemetry" detail="Map read-only live telemetry into operational relationships." status="Planned" />
          <SourceCard label="OPC-UA" detail="Read industrial tags from OPC-UA endpoints without control-system writeback." status="Planned" />
          <SourceCard label="MQTT" detail="Subscribe to broker topics for telemetry-only monitoring." status="Planned" />
          <SourceCard label="PI System" detail="Connect historian data for baseline windows and current behavior comparisons." status="Planned" />
          <SourceCard label="SCADA/BMS connectors" detail="Read-only integrations above existing facility systems." status="Planned" />
        </div>
      </section>
      <section className="operational-panel operational-panel--wide" aria-label="Data source status">
        <PanelHeader eyebrow="Status" title="Current Source Status" subtitle="" />
        <DetailGrid rows={model.dataSourceRows} />
      </section>
    </div>
  );
}

function SourceCard({ label, detail, status, available = false, onClick }) {
  return (
    <button
      type="button"
      className={available ? "telemetry-source-card telemetry-source-card--available" : "telemetry-source-card"}
      onClick={available ? onClick : undefined}
      disabled={!available}
    >
      <strong>{label}</strong>
      <span>{detail}</span>
      <small>{status}</small>
    </button>
  );
}
