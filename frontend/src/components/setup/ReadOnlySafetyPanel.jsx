import { Panel } from "../workspacePrimitives";

export default function ReadOnlySafetyPanel() {
  return (
    <Panel title="Read-only Safety Statement" className="span-4">
      <p>
        Neraium connects read-only. It does not write to the telemetry source, change control values, issue commands, or control equipment.
      </p>
    </Panel>
  );
}
