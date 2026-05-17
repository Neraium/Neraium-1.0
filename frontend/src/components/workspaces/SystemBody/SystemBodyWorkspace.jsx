import SystemOrbPanel from "./SystemOrbPanel";
import SystemNarrativePanel from "./SystemNarrativePanel";
import SystemEvidencePanel from "./SystemEvidencePanel";
import SystemDiagnosticsPanel from "./SystemDiagnosticsPanel";
import PageContainer from "../../layout/PageContainer";
import { EMPTY_VALUE } from "../../../viewModels/emptyValue";

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
  lifecycleRail = [],
  isLoading = false,
}) {
  void isLoading;

  const operatorFocus =
    narrativeItems?.find((item) => item.label?.toLowerCase().includes("operator"))?.value
    || EMPTY_VALUE;

  return (
    <PageContainer className="system-body system-body--orb-first system-body--mobile-polished">
      <section className={`system-body-hero hero-panel system-body-hero--${systemState} ui-state-surface ui-state-surface--${uiState}`}>
        <div className="system-body-hero__copy">
          {lifecycleRail.length > 0 ? (
            <div className="system-status-rail" aria-label="Operational lifecycle status rail">
              {lifecycleRail.map((item) => (
                <article className="system-status-rail__item" key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.status}</strong>
                </article>
              ))}
            </div>
          ) : null}
          <header className="system-body-hero__header">
            <p className="workspace-header__kicker">Primary System State</p>
            <h2 className="workspace-header__title">{stateLabel || EMPTY_VALUE}</h2>
            <p className="workspace-header__subtitle">{primaryMessage || subtitle || EMPTY_VALUE}</p>

            <div className="system-body-action-strip">
              <span>Operator Focus</span>
              <strong>{operatorFocus}</strong>
            </div>

            <div className="system-body-status-row">
              <div className={`workspace-header__status workspace-header__status--${connectionTone}`}>
                <span className="metadata-text">Focus area</span>
                <strong>{focusLabel || EMPTY_VALUE}</strong>
              </div>
              <div className="workspace-header__status">
                <span className="metadata-text">Updated</span>
                <strong>{lastUpdate || connectionStatus || EMPTY_VALUE}</strong>
              </div>
            </div>
          </header>

          <SystemNarrativePanel
            summaryKicker="Operator Summary"
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

      <SystemEvidencePanel
        evidenceItems={evidenceItems}
        timelineItems={timelineItems}
        uiState={uiState}
      />

      <SystemDiagnosticsPanel metrics={metrics} uiState={uiState} />
    </PageContainer>
  );
}
