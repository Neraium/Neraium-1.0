import { DataTable, Panel } from "../workspacePrimitives";

export default function TagMappingPanel({ rows, onContinue = null }) {
  return (
    <Panel title="Tag Mapping" className="span-12">
      <p className="narrative-text">
        Signal mapping is review-only in the pilot flow. Use the continue action below to move straight into baseline building.
      </p>
      <DataTable
        columns={["Raw Tag", "Normalized Name", "Subsystem", "Equipment", "Unit", "Sample Rate", "Quality"]}
        rows={rows}
      />
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
