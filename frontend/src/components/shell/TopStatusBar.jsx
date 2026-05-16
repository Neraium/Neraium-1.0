import React from "react";

export default function TopStatusBar({
  activeConfig,
  latestUploadResult,
  roomContext,
  liveOps,
  isDemoMode,
  onToggleDemoMode,
  demoScenario,
  onSetDemoScenario,
  StatusDot,
  StatusChip,
  deriveTriageSummary,
  formatIntelligenceSourceLabel,
  formatReadiness,
}) {
  const intelligenceLabel = formatIntelligenceSourceLabel(liveOps.intelligenceMode);
  const triageSummary = deriveTriageSummary(liveOps, roomContext);

  return (
    <header className="top-status">
      <div className="top-status__title">
        <p className="eyebrow">Neraium Command - {activeConfig.eyebrow}</p>
        <h1 id="page-title">{activeConfig.label}</h1>
        <p>{activeConfig.description}</p>
        <div className="top-status__meta">
          <span className={`top-status__signal top-status__signal--${liveOps.connectionTone}`} aria-label={liveOps.connectionStatusLine}>
            <StatusDot tone={liveOps.connectionTone} />
          </span>
          <span className={`sii-source-chip sii-source-chip--${liveOps.intelligenceMode}`}>{intelligenceLabel}</span>
          {liveOps.connectionActionHint && (
            <span className="top-status__meta-copy top-status__meta-copy--actionable">{liveOps.connectionActionHint}</span>
          )}
        </div>
      </div>
      <div className={`top-status__brief top-status__brief--${liveOps.facilityTone}`}>
        <article className="top-status__brief-item"><span>Current condition</span><strong>{triageSummary.problem}</strong></article>
        <article className="top-status__brief-item"><span>Where</span><strong>{triageSummary.where}</strong></article>
        <article className="top-status__brief-item top-status__brief-item--wide"><span>Evidence confidence</span><p>{triageSummary.why}</p></article>
        <article className="top-status__brief-item top-status__brief-item--wide"><span>Operator action focus</span><p>{triageSummary.human}</p></article>
      </div>
      <div className="status-rack">
        <StatusChip label="Severity" value={liveOps.facilityStateLabel} tone={liveOps.facilityTone} />
        <StatusChip label="Primary room" value={roomContext.primary} tone={liveOps.facilityTone} />
        <StatusChip label="Continuation window" value={liveOps.primaryWindow?.label ?? "Facility overview"} tone={liveOps.primaryWindow?.tone ?? "info"} />
        <StatusChip
          label="Structural update"
          value={latestUploadResult?.data_quality ? formatReadiness(latestUploadResult.data_quality?.readiness) : liveOps.readinessLabel}
          tone={latestUploadResult?.data_quality?.readiness ?? liveOps.connectionTone}
        />
        <button className="secondary-command-button" type="button" onClick={onToggleDemoMode}>{isDemoMode ? "Sample On" : "Sample Off"}</button>
        {isDemoMode && (
          <>
            <button className={`secondary-command-button ${demoScenario === "stable" ? "is-active" : ""}`} type="button" onClick={() => onSetDemoScenario("stable")}>Stable</button>
            <button className={`secondary-command-button ${demoScenario === "drift" ? "is-active" : ""}`} type="button" onClick={() => onSetDemoScenario("drift")}>Drift</button>
            <button className={`secondary-command-button ${demoScenario === "separation" ? "is-active" : ""}`} type="button" onClick={() => onSetDemoScenario("separation")}>Separation</button>
          </>
        )}
      </div>
    </header>
  );
}
