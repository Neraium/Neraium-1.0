import { MetricGrid, Panel } from "../workspacePrimitives";

export default function BaselineWindowPanel() {
  return (
    <Panel title="Reference Window" className="span-8">
      <MetricGrid
        metrics={[
          { label: "Historical Reference", value: "30 to 90 days recommended" },
          { label: "Recent Comparison", value: "15 minutes to 24 hours" },
          { label: "Context: Alarms", value: "Optional input channel" },
          { label: "Context: Maintenance Logs", value: "Optional input channel" },
          { label: "Context: Setpoint Changes", value: "Optional input channel" },
          { label: "Context: Weather + Load", value: "Optional input channel" },
        ]}
      />
    </Panel>
  );
}
