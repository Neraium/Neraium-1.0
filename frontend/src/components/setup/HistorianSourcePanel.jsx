import { MetricGrid, Panel } from "../workspacePrimitives";

export default function HistorianSourcePanel() {
  return (
    <Panel title="Historian Source" className="span-6">
      <MetricGrid
        metrics={[
          { label: "Source Type", value: "AVEVA / OSIsoft PI, Ignition, Niagara/BACnet, SQL historian, InfluxDB/TimescaleDB, CSV/S3/Blob" },
          { label: "Host / Endpoint", value: "Configured per pilot environment" },
          { label: "Authentication", value: "Token / basic / service account (read-only scope)" },
          { label: "Polling Interval", value: "1 to 15 minutes" },
          { label: "Timezone", value: "Facility local timezone" },
          { label: "Retention Window", value: "30 to 90 day baseline capture" },
        ]}
      />
    </Panel>
  );
}
