import SystemOrbPanel from "./SystemOrbPanel";
import SystemNarrativePanel from "./SystemNarrativePanel";
import SystemMetricGrid from "./SystemMetricGrid";
import SystemEvidencePanel from "./SystemEvidencePanel";
import PageContainer from "../../layout/PageContainer";
import SystemBodySkeleton from "../../loading/SystemBodySkeleton";

export default function SystemBodyWorkspace({
  systemState,
  uiState,
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
  void primaryMessage;

  if (isLoading) {
    return (
      <PageContainer className="system-body system-body--orb-first">
        <SystemBodySkeleton />
      </PageContainer>
    );
  }

  return (
    <PageContainer className="system-body system-body--orb-first">
      <section className={`system-body-hero hero-panel system-body-hero--${systemState} ui-state-surface ui-state-surface--${uiState}`}>
        <div className="system-body-hero__copy">
          <header className="system-body-hero__header">
            <p className="workspace-header__kicker">System Body</p>
            <h2 className="workspace-header__title">{stateLabel}</h2>
            <p className="workspace-header__subtitle">{subtitle}</p>
            <div className={`workspace-header__status workspace-header__status--${connectionTone}`}>
              <span className="metadata-text">Connection status</span>
              <strong>{connectionStatus}</strong>
            </div>
          </header>
          <SystemNarrativePanel
            summaryKicker="Operational narrative"
            summaryTitle={summaryTitle}
            items={narrativeItems}
            uiState={uiState}
          />
        </div>
        <SystemOrbPanel
          systemState={systemState}
          uiState={uiState}
          coherence={coherence}
          stateLabel={stateLabel}
        />
      </section>
      <SystemMetricGrid metrics={metrics} />
      <SystemEvidencePanel evidenceItems={evidenceItems} timelineItems={timelineItems} uiState={uiState} />
    </PageContainer>
  );
}
