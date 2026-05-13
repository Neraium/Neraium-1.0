import HealthOrb from "../../HealthOrb";

export default function SystemOrbPanel({ systemState, coherence, stateLabel }) {
  return (
    <aside className={`system-body-orb-panel system-body-orb-panel--${systemState}`} aria-label="Facility condition orb">
      <div className="system-body-orb-panel__halo system-body-orb-panel__halo--outer" />
      <div className="system-body-orb-panel__halo system-body-orb-panel__halo--inner" />
      <div className="system-body-orb-panel__depth" />
      <div className="system-body-orb-panel__stage">
        <HealthOrb systemState={systemState} intensity={1 - coherence} />
      </div>
      <div className="system-body-orb-panel__meta">
        <span className="section-label">Facility condition</span>
        <strong>{stateLabel}</strong>
      </div>
    </aside>
  );
}
