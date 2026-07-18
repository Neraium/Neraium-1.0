import { DataTable, Panel } from "../workspacePrimitives";

export default function TagMappingPanel({ rows, onContinue = null }) {
  const signalRoles = [
    { label: "Time context", pattern: /time|date|timestamp|recorded/i },
    { label: "Operating signal", pattern: /signal|metric|load|runtime|status|state|command|setpoint|value|temperature|pressure|flow|power|current|voltage|level|quality|speed/i },
    { label: "Response signal", pattern: /response|output|return|feedback|result|delta|efficiency|quality|temperature|pressure|flow|power|level/i },
    { label: "Equipment or system context", pattern: /equipment|asset|system|area|zone|room|line|loop|panel|controller|station|unit|segment/i },
  ];
  const normalizedNames = (rows ?? []).flatMap((row) => row).map((value) => String(value ?? "").toLowerCase().trim());
  const mappedRequiredCount = signalRoles.filter((role) => normalizedNames.some((name) => role.pattern.test(name))).length;
  const mappingHealth = rows.length > 0 ? Math.round((mappedRequiredCount / signalRoles.length) * 100) : 0;

  return (
    <Panel title="Tag Mapping" className="span-12">
      <p className="narrative-text">
        Review signal-role coverage, then continue. Full mapping detail is available below.
      </p>
      <div className="intake-flow__controls" style={{ alignItems: "flex-start", flexDirection: "column", gap: 6 }}>
        <p className="narrative-text">Mapped signals: {rows.length}</p>
        <p className="narrative-text">Signal-role coverage: {mappedRequiredCount}/{signalRoles.length} ({mappingHealth}%)</p>
      </div>
      <details className="technical-detail-panel">
        <summary>View full mapping table</summary>
        <DataTable
          columns={["Raw Tag", "Normalized Name", "Operational System", "Equipment or Asset", "Unit", "Sample Rate", "Quality"]}
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
