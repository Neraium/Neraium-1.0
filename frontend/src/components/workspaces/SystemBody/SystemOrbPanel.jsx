import HealthOrb from "../../HealthOrb";

export default function SystemOrbPanel({ systemState, uiState, coherence, stateLabel }) {
  const resolvedSystemState = systemState || "neutral";
  const resolvedUiState = uiState || "neutral";
  const resolvedCoherence = Number.isFinite(coherence) ? coherence : 1;
  const resolvedLabel = stateLabel || "Awaiting baseline";

  return (
    <aside className={`system-body-orb-panel system-body-orb-panel--${resolvedSystemState} ui-state-indicator ui-state-indicator--${resolvedUiState}`} aria-label="Facility condition orb">
      <div className="system-body-orb-panel__halo system-body-orb-panel__halo--outer" />
      <div className="system-body-orb-panel__halo system-body-orb-panel__halo--inner" />
      <div className="system-body-orb-panel__depth" />
      <div className="system-body-orb-panel__stage">
        <HealthOrb systemState={resolvedSystemState} intensity={1 - resolvedCoherence} />
      </div>
      <div className="system-body-orb-panel__meta">
        <span className="section-label">Facility condition</span>
        <strong>{resolvedLabel}</strong>
      </div>
    </aside>
  );
}
