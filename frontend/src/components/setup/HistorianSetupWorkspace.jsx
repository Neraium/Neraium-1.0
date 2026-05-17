import { DataTable, Panel } from "../workspacePrimitives";
import ConnectionModeCards from "./ConnectionModeCards";
import HistorianSourcePanel from "./HistorianSourcePanel";
import TagMappingPanel from "./TagMappingPanel";
import BaselineWindowPanel from "./BaselineWindowPanel";
import ReadOnlySafetyPanel from "./ReadOnlySafetyPanel";

export default function HistorianSetupWorkspace({ tagMapRows }) {
  return (
    <>
      <Panel title="Historian Intake Architecture" className="span-12 workspace-hero-panel">
        <DataTable
          columns={["Pipeline Stage"]}
          rows={[
            ["Historian / BMS / SCADA"],
            ["read-only ingestion"],
            ["Neraium Intake Connector"],
            ["Tag Mapper + Normalizer"],
            ["Baseline Builder"],
            ["Live Structural Analysis"],
            ["Operator UI / Reports"],
          ]}
        />
      </Panel>
      <ConnectionModeCards />
      <HistorianSourcePanel />
      <TagMappingPanel rows={tagMapRows} />
      <BaselineWindowPanel />
      <ReadOnlySafetyPanel />
    </>
  );
}
