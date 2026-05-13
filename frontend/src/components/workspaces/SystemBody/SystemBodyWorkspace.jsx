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
  subtitle,
  connectionStatus,
  connectionTone,
  primaryMessage,
  summaryTitle,
  narrativeItems,
  metrics,
  evidenceItems,
  timelineItems,
  isLoading = false,
}) {
  if (isLoading) {
    return (
      <PageContainer className="system-body system-body--orb-first">
        <WorkspaceHeader
          kicker="System Body"
          title={stateLabel}
          subtitle={subtitle}
          description="Synchronizing facility telemetry and structural intelligence."
          statusLabel={connectionStatus}
          statusTone={connectionTone}
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
        subtitle={subtitle}
        description={primaryMessage}
        statusLabel={connectionStatus}
        statusTone={connectionTone}
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
        items={narrativeItems}
      />
      <SystemMetricGrid metrics={metrics} />
      <SystemEvidencePanel evidenceItems={evidenceItems} timelineItems={timelineItems} />
    </PageContainer>
  );
}
