import SystemOrbPanel from "./SystemOrbPanel";
import SystemNarrativePanel from "./SystemNarrativePanel";
import SystemMetricGrid from "./SystemMetricGrid";
import SystemEvidencePanel from "./SystemEvidencePanel";
import PageContainer from "../../layout/PageContainer";

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
  lastUpdate,
  focusLabel,
  isLoading = false,
}) {
  void primaryMessage;
  void isLoading;

  return (
    <PageContainer className="system-body system-body--orb-first">
      <section className={`system-body-hero hero-panel system-body-hero--${systemState} ui-state-surface ui-state-surface--${uiState}`}>
        <div className="system-body-hero__copy">
          <header className="system-body-hero__header">
            <p className="workspace-header__kicker">Primary System State</p>
            <h2 className="workspace-header__title">{stateLabel}</h2>
            <p className="workspace-header__subtitle">{subtitle}</p>
            <div className={`workspace-header__status workspace-header__status--${connectionTone}`}>
              <span className="metadata-text">Connection status</span>
              <strong>{connectionStatus}</strong>
            </div>
          </header>
          <SystemNarrativePanel
            summaryKicker="Operational Summary"
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
          lastUpdate={lastUpdate}
          focusLabel={focusLabel}
        />
      </section>
      <SystemMetricGrid metrics={metrics} />
      <SystemEvidencePanel evidenceItems={evidenceItems} timelineItems={timelineItems} uiState={uiState} />
    </PageContainer>
  );
}
