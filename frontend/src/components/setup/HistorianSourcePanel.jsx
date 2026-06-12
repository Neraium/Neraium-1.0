import { MetricGrid, Panel } from "../workspacePrimitives";

export default function HistorianSourcePanel() {
  return (
    <Panel title="Telemetry Source" className="span-6">
      <MetricGrid
        metrics={[
          { label: "Source Type", value: "Read-only API, stream broker, SQL/TSDB, industrial connector, or CSV/S3/Blob" },
          { label: "Host / Endpoint", value: "Configured per pilot environment" },
          { label: "Authentication", value: "Token / basic / service account (read-only scope)" },
          { label: "Polling Interval", value: "1 to 15 minutes" },
          { label: "Timezone", value: "Deployment local timezone" },
          { label: "Retention Window", value: "30 to 90 day reference capture" },
        ]}
      />
    </Panel>
  );
}
