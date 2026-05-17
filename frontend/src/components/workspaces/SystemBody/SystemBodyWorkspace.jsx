import React, { useState } from "react";
import SystemOrbPanel from "./SystemOrbPanel";
import SystemNarrativePanel from "./SystemNarrativePanel";
import SystemEvidencePanel from "./SystemEvidencePanel";
import SystemDiagnosticsPanel from "./SystemDiagnosticsPanel";
import MobileStructuralEmptyState from "./MobileStructuralEmptyState";
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
  orbData = null,
  statusLight = "gray",
  governedOnly = false,
  governedDetail = null,
  isLoading = false,
  isEmptyStructuralState = false,
}) {
  void isLoading;
  const [detailOpen, setDetailOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const hasAdmittedFinding = statusLight !== "gray";

  const operatorFocus =
    narrativeItems?.find((item) => item.label?.toLowerCase().includes("operator"))?.value
    || EMPTY_VALUE;

  if (governedOnly) {
    return (
      <PageContainer className="system-body system-body--gate">
        <section className={`system-gate ui-state-surface ui-state-surface--${uiState}`} aria-label="The Gate">
          <button type="button" className="system-gate__settings" aria-label="Open Gate settings" onClick={() => setSettingsOpen((v) => !v)}>
            SET
          </button>
          <div className="system-gate__center" role="button" tabIndex={0} onClick={() => hasAdmittedFinding && setDetailOpen(true)} onKeyDown={(event) => {
            if ((event.key === "Enter" || event.key === " ") && hasAdmittedFinding) {
              event.preventDefault();
              setDetailOpen(true);
            }
          }}>
            <h2 className="system-gate__title">The Gate</h2>
            <SystemOrbPanel
              systemState={systemState}
              uiState={uiState}
              coherence={coherence}
              stateLabel={stateLabel}
              lastUpdate={lastUpdate}
              focusLabel={focusLabel}
              orbData={null}
              compactPreview
            />
            <p className="system-gate__state">{stateLabel || EMPTY_VALUE}</p>
            <p className="system-gate__timestamp">{lastUpdate || connectionStatus || EMPTY_VALUE}</p>
            <p className="system-gate__inspect">Tap to Inspect</p>
          </div>
          {settingsOpen ? (
            <aside className="system-gate__settings-panel" aria-label="Gate settings panel">
              <ul>
                <li>Upload historical data</li>
                <li>Connect live data source</li>
                <li>Configure deployment settings</li>
                <li>Governance/admin access</li>
              </ul>
            </aside>
          ) : null}
          {detailOpen && hasAdmittedFinding && governedDetail ? (
            <aside className="system-gate__detail" aria-label="Governed admitted detail view">
              <header>
                <strong>Admitted Finding</strong>
                <button type="button" className="btn btn--secondary" onClick={() => setDetailOpen(false)}>Close</button>
              </header>
              <ul>
                <li><span>Why</span><strong>{governedDetail.evidenceSummary || EMPTY_VALUE}</strong></li>
                <li><span>Where</span><strong>{governedDetail.affectedSubsystem || EMPTY_VALUE}</strong></li>
                <li><span>Persistence Count</span><strong>{governedDetail.persistenceConfirmation || EMPTY_VALUE}</strong></li>
                <li><span>Trajectory</span><strong>{governedDetail.telemetryWindowReferences || EMPTY_VALUE}</strong></li>
                <li><span>Recovery Window Status</span><strong>{governedDetail.persistenceConfirmation || EMPTY_VALUE}</strong></li>
                <li><span>Subsystem Affected</span><strong>{governedDetail.affectedSubsystem || EMPTY_VALUE}</strong></li>
                <li><span>Structural Relationship Evidence</span><strong>{governedDetail.structuralRelationshipEvidence || EMPTY_VALUE}</strong></li>
                <li><span>Operator Focus</span><strong>{governedDetail.operatorFocus || EMPTY_VALUE}</strong></li>
                <li><span>EVP Reference</span><strong>{governedDetail.evpPreview || EMPTY_VALUE}</strong></li>
              </ul>
            </aside>
          ) : null}
        </section>
      </PageContainer>
    );
  }

  return (
    <PageContainer className={`system-body system-body--orb-first system-body--mobile-polished ${isEmptyStructuralState ? "system-body--empty-structural" : ""}`}>
      {isEmptyStructuralState ? <MobileStructuralEmptyState lifecycleRail={lifecycleRail} /> : null}

      <div className="system-body-standard-shell">
      <section className={`system-body-hero hero-panel system-body-hero--${systemState} ui-state-surface ui-state-surface--${uiState}`}>
        <div className="system-body-hero__copy">
          <header className="system-body-hero__header">
            <p className="workspace-header__kicker">Governed Operator State</p>
            <h2 className="workspace-header__title">{stateLabel || EMPTY_VALUE}</h2>
            <p className="workspace-header__subtitle">{primaryMessage || subtitle || EMPTY_VALUE}</p>
            <div className="system-body-status-light" aria-label="Governed status light">
              <span className={`system-body-status-light__dot system-body-status-light__dot--${statusLight}`} />
              <strong>{statusLightLabel(statusLight)}</strong>
            </div>

            <div className="system-body-action-strip">
              <span>Operator Focus</span>
              <strong>{operatorFocus}</strong>
            </div>
          </header>

          <div className="system-body-summary-desktop">
            {governedOnly ? (
              <section className={`system-body-governed-summary ui-state-surface ui-state-surface--${uiState}`}>
                <div className="system-body-governed-summary__header">
                  <span className="section-label">Governed Operator View</span>
                  <button type="button" className="btn btn--secondary" onClick={() => setDetailOpen((v) => !v)}>
                    {detailOpen ? "Hide Governed Detail" : "Open Governed Detail"}
                  </button>
                </div>
                <ul className="system-body-governed-summary__list">
                  {narrativeItems.map((item) => (
                    <li key={item.label}><span>{item.label}</span><strong>{item.value}</strong></li>
                  ))}
                </ul>
                {detailOpen && governedDetail ? (
                  <div className="system-body-governed-detail">
                    <ul>
                      <li><span>Admitted State</span><strong>{governedDetail.admittedState || EMPTY_VALUE}</strong></li>
                      <li><span>Evidence Summary</span><strong>{governedDetail.evidenceSummary || EMPTY_VALUE}</strong></li>
                      <li><span>Persistence Confirmation</span><strong>{governedDetail.persistenceConfirmation || EMPTY_VALUE}</strong></li>
                      <li><span>Doctrine Version</span><strong>{governedDetail.doctrineVersion || EMPTY_VALUE}</strong></li>
                      <li><span>Affected Subsystem</span><strong>{governedDetail.affectedSubsystem || EMPTY_VALUE}</strong></li>
                      <li><span>Structural Relationship Evidence</span><strong>{governedDetail.structuralRelationshipEvidence || EMPTY_VALUE}</strong></li>
                      <li><span>Operator Focus</span><strong>{governedDetail.operatorFocus || EMPTY_VALUE}</strong></li>
                      <li><span>Telemetry Window References</span><strong>{governedDetail.telemetryWindowReferences || EMPTY_VALUE}</strong></li>
                      <li><span>EVP ID/Hash</span><strong>{governedDetail.evpPreview || EMPTY_VALUE}</strong></li>
                    </ul>
                  </div>
                ) : null}
              </section>
            ) : (
              <SystemNarrativePanel
                summaryKicker="Operator Summary"
                summaryTitle={summaryTitle}
                items={narrativeItems}
                uiState={uiState}
              />
            )}
          </div>
        </div>

        <SystemOrbPanel
          systemState={systemState}
          uiState={uiState}
          coherence={coherence}
          stateLabel={stateLabel}
          lastUpdate={lastUpdate}
          focusLabel={focusLabel}
          orbData={orbData}
        />
      </section>

      {governedOnly ? null : (
        <SystemEvidencePanel
          evidenceItems={evidenceItems}
          timelineItems={timelineItems}
          uiState={uiState}
        />
      )}

      {governedOnly ? null : (
        <details className="system-body-summary-mobile">
          <summary>Operator Summary</summary>
          <SystemNarrativePanel
            summaryKicker="Operator Summary"
            summaryTitle={summaryTitle}
            items={narrativeItems}
            uiState={uiState}
          />
        </details>
      )}

      {governedOnly ? null : <SystemDiagnosticsPanel metrics={metrics} uiState={uiState} />}
      </div>
    </PageContainer>
  );
}

function statusLightLabel(light) {
  if (light === "green") return "Governed Stable";
  if (light === "yellow") return "Governed Watch";
  if (light === "red") return "Governed Alert";
  return "No Governed Finding";
}
