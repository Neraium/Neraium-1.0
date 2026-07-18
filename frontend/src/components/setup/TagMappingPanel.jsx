import { DataTable, Panel } from "../workspacePrimitives";

export default function TagMappingPanel({ rows, onContinue = null }) {
  const requiredSignals = ["ORP", "pH", "flow_rate", "filter_pressure", "pump_amperage"];
  const normalizedNames = new Set((rows ?? []).map((row) => String(row?.[1] ?? "").toLowerCase().trim()));
  const mappedRequiredCount = requiredSignals.filter((signal) => normalizedNames.has(signal.toLowerCase())).length;
  const mappingHealth = rows.length > 0 ? Math.round((mappedRequiredCount / requiredSignals.length) * 100) : 0;

  return (
    <Panel title="Tag Mapping" className="span-12">
      <p className="narrative-text">
        Review required signal coverage, then continue. Full mapping detail is available below.
      </p>
      <div className="intake-flow__controls" style={{ alignItems: "flex-start", flexDirection: "column", gap: 6 }}>
        <p className="narrative-text">Mapped signals: {rows.length}</p>
        <p className="narrative-text">Required signal coverage: {mappedRequiredCount}/{requiredSignals.length} ({mappingHealth}%)</p>
      </div>
      <details className="technical-detail-panel">
        <summary>View full mapping table</summary>
        <DataTable
          columns={["Raw Tag", "Normalized Name", "Subsystem", "Equipment", "Unit", "Sample Rate", "Quality"]}
          rows={rows}
        />
      </details>
      {typeof onContinue === "function" ? (
        <div className="intake-flow__controls">
          <button type="button" className="command-button" onClick={onContinue}>
            Continue to Baseline Builder
          </button>
        </div>
      ) : null}
    </Panel>
  );
}
