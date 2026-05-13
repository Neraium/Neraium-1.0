import SystemOrbPanel from "./SystemOrbPanel";
import SystemNarrativePanel from "./SystemNarrativePanel";
import SystemMetricGrid from "./SystemMetricGrid";
import SystemEvidencePanel from "./SystemEvidencePanel";
import "../../../styles/workspace-system-body.css";

export default function SystemBodyWorkspace({
  systemState,
  coherence,
  stateLabel,
  primaryMessage,
  summaryTitle,
  summaryText,
  metrics,
  evidenceItems,
}) {
  return (
    <section className="system-body system-body--orb-first">
      <SystemOrbPanel
        systemState={systemState}
        coherence={coherence}
        stateLabel={stateLabel}
        primaryMessage={primaryMessage}
      />
      <SystemNarrativePanel
        summaryKicker="Operational summary"
        summaryTitle={summaryTitle}
        summaryText={summaryText}
      />
      <SystemMetricGrid metrics={metrics} />
      <SystemEvidencePanel evidenceItems={evidenceItems} />
    </section>
  );
}
