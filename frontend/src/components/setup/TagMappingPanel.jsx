import { DataTable, Panel } from "../workspacePrimitives";

export default function TagMappingPanel({ rows }) {
  return (
    <Panel title="Tag Mapping" className="span-12">
      <DataTable
        columns={["Raw Tag", "Normalized Name", "Subsystem", "Equipment", "Unit", "Sample Rate", "Quality"]}
        rows={rows}
      />
    </Panel>
  );
}
