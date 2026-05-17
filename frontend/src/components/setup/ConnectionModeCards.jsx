import { MetricGrid, Panel } from "../workspacePrimitives";

export default function ConnectionModeCards() {
  return (
    <Panel title="Connection Mode" className="span-6">
      <MetricGrid
        metrics={[
          { label: "CSV Export Pilot", value: "Pilot Ready Â· Read-only ingest only" },
          { label: "Read-only Historian API", value: "Available Â· No control path" },
          { label: "Scheduled Pull", value: "Available Â· Pull-only ingestion window" },
          { label: "Live Stream / MQTT", value: "Future Â· Read-only subscription model" },
        ]}
      />
    </Panel>
  );
}
