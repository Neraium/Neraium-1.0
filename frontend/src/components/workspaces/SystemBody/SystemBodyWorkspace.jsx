import SystemOrbPanel from "./SystemOrbPanel";
import SystemNarrativePanel from "./SystemNarrativePanel";
import SystemMetricGrid from "./SystemMetricGrid";
import SystemEvidencePanel from "./SystemEvidencePanel";
import PageContainer from "../../layout/PageContainer";
import WorkspaceHeader from "../../layout/WorkspaceHeader";

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
    <PageContainer className="system-body system-body--orb-first">
      <WorkspaceHeader
        kicker="System Body"
        title={stateLabel}
        description={primaryMessage}
      />
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
    </PageContainer>
  );
}
