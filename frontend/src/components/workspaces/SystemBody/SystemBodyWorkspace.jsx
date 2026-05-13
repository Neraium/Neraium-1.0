import SystemOrbPanel from "./SystemOrbPanel";
import SystemNarrativePanel from "./SystemNarrativePanel";
import SystemMetricGrid from "./SystemMetricGrid";
import SystemEvidencePanel from "./SystemEvidencePanel";
import PageContainer from "../../layout/PageContainer";
import WorkspaceHeader from "../../layout/WorkspaceHeader";
import SystemBodySkeleton from "../../loading/SystemBodySkeleton";

export default function SystemBodyWorkspace({
  systemState,
  coherence,
  stateLabel,
  primaryMessage,
  summaryTitle,
  summaryText,
  metrics,
  evidenceItems,
  isLoading = false,
}) {
  if (isLoading) {
    return (
      <PageContainer className="system-body system-body--orb-first">
        <WorkspaceHeader
          kicker="System Body"
          title={stateLabel}
          description="Synchronizing facility telemetry and structural intelligence."
        />
        <SystemBodySkeleton />
      </PageContainer>
    );
  }

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
