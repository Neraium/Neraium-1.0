const AVAILABLE_IMPORTS = [
  {
    icon: "CSV",
    label: "CSV dataset import",
    detail: "Timestamped telemetry dataset for one analysis.",
    status: "Available",
  },
];

const PLANNED_CONNECTORS = [
  { icon: "OPC", label: "OPC UA", detail: "Planned read-only connector for industrial telemetry." },
  { icon: "MQ", label: "MQTT", detail: "Planned read-only connector for broker telemetry." },
  { icon: "BAC", label: "BACnet", detail: "Planned read-only connector for building automation telemetry." },
  { icon: "HIS", label: "Enterprise historians", detail: "Planned read-only connectors for historian telemetry." },
];

export default function DataSourcesView({ model, helpers, onAnalyzeHistoricalData, importCardRef }) {
  const { DetailGrid, PanelHeader, StatusBadge } = helpers;
  const sourceHealth = model.telemetryConnected
    ? { label: "Connector healthy", tone: "active", statusKey: "active" }
    : model.datasetImported
      ? { label: "Dataset imported", tone: "ready", statusKey: "ready" }
      : null;
  const configuredConnectors = model.telemetryConnected
    ? [
        {
          icon: "LIVE",
          label: model.connectorLabel || "Live telemetry connector",
          status: "Configured",
          rows: [
            ["Health", "Healthy"],
            ["Access", "Read-only"],
          ],
        },
      ]
    : [];

  if (!model.datasetImported) {
    return (
      <div className="operational-grid operational-grid--data-sources data-sources-no-dataset">
        <section
          ref={importCardRef}
          id="import-dataset"
          className="operational-panel operational-panel--wide data-source-import-card"
          aria-labelledby="import-dataset-heading"
          tabIndex={-1}
        >
          <div className="data-source-import-card__copy">
            <h2 id="import-dataset-heading">Import a dataset</h2>
            <p>Upload timestamped CSV telemetry to establish a baseline and run the first analysis.</p>
          </div>
          <button
            type="button"
            className="command-button data-source-import-card__button"
            onClick={onAnalyzeHistoricalData}
            disabled={model.analyzeDisabled}
            title={model.analyzeDisabled ? "Analysis is already in progress. Wait for it to finish before starting another." : "Choose a timestamped telemetry CSV file."}
          >
            Choose CSV file
          </button>
        </section>

        <section className="operational-panel operational-panel--wide data-source-status-panel" aria-label="Data Source Status">
          <PanelHeader title="Data Source Status" />
          {sourceHealth ? <StatusBadge label={sourceHealth.label} tone={sourceHealth.tone} statusKey={sourceHealth.statusKey} /> : null}
          <DetailGrid rows={model.dataSourceRows} />
        </section>

        <section className="operational-panel" aria-label="Configured connectors">
          <PanelHeader title="Configured connectors" />
          {configuredConnectors.length ? (
            <div className="telemetry-source-grid telemetry-source-grid--compact">
              {configuredConnectors.map((connector) => (
                <ConnectorCard key={connector.label} {...connector} configured />
              ))}
            </div>
          ) : (
            <div className="connector-empty-row connector-empty-row--stacked" role="status">
              <strong>No configured connectors</strong>
              <span>Connectors can be added when continuous read-only telemetry is needed.</span>
            </div>
          )}
        </section>

        <section className="operational-panel data-source-planned-panel" aria-label="Planned connectors">
          <PanelHeader title="Planned connectors" />
          <div className="telemetry-source-grid telemetry-source-grid--compact">
            {PLANNED_CONNECTORS.map((source) => (
              <ConnectorCard key={source.label} {...source} status="Planned" />
            ))}
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="operational-grid operational-grid--data-sources">
      <section className="operational-panel operational-panel--wide data-source-status-panel" aria-label="Data Source Status">
        <PanelHeader
          eyebrow="Status"
          title="Data Source Status"
        />
        <StatusBadge label={sourceHealth.label} tone={sourceHealth.tone} statusKey={sourceHealth.statusKey} />
        <DetailGrid rows={model.dataSourceRows} />
      </section>

      <section className="operational-panel operational-panel--wide data-source-actions-panel" aria-label="Dataset Analysis">
        <PanelHeader eyebrow="Primary Action" title="Import and Analyze a Dataset" />
        <div className="data-source-action-grid data-source-action-grid--single">
          <button type="button" className="command-button data-source-action data-source-action--primary" onClick={onAnalyzeHistoricalData} disabled={model.analyzeDisabled} title={model.analyzeDisabled ? "Analysis is already in progress. Wait for it to finish before starting another." : "Choose a telemetry CSV to analyze."}>
            <strong>Choose Dataset</strong>
            <span>Import CSV telemetry and run analysis.</span>
          </button>
        </div>
      </section>

      <section className="operational-panel" aria-label="Available Imports">
        <PanelHeader eyebrow="Imports" title="Available Imports" />
        <div className="telemetry-source-grid telemetry-source-grid--compact">
          {AVAILABLE_IMPORTS.map((source) => (
            <ConnectorCard key={source.label} {...source} available />
          ))}
        </div>
      </section>

      <section className="operational-panel" aria-label="Configured Connectors">
        <PanelHeader eyebrow="Connectors" title="Configured Connectors" />
        {configuredConnectors.length ? (
          <div className="telemetry-source-grid telemetry-source-grid--compact">
            {configuredConnectors.map((connector) => (
              <ConnectorCard key={connector.label} {...connector} configured />
            ))}
          </div>
        ) : (
          <div className="connector-empty-row" role="status">
            <strong>No configured connectors</strong>
            <span>CSV import is available.</span>
          </div>
        )}
      </section>

      <section className="operational-panel" aria-label="Planned Connectors">
        <PanelHeader eyebrow="Connectors" title="Planned Connectors" />
        <div className="telemetry-source-grid telemetry-source-grid--compact">
          {PLANNED_CONNECTORS.map((source) => (
            <ConnectorCard key={source.label} {...source} status="Planned" />
          ))}
        </div>
      </section>
    </div>
  );
}

function ConnectorCard({ icon, label, detail, status, rows = [], available = false, configured = false }) {
  return (
    <article className={available || configured ? "telemetry-source-card telemetry-source-card--available" : "telemetry-source-card telemetry-source-card--planned"}>
      <div className="telemetry-source-card__header">
        <span className="telemetry-source-card__icon" aria-hidden="true">{icon}</span>
        <small>{status}</small>
      </div>
      <strong>{label}</strong>
      {detail ? <span>{detail}</span> : null}
      {rows.length ? (
        <dl className="connector-compact-rows">
          {rows.map(([rowLabel, value]) => (
            <div key={rowLabel}>
              <dt>{rowLabel}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </article>
  );
}
