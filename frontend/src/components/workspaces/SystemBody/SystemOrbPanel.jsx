import HealthOrb from "../../HealthOrb";

export default function SystemOrbPanel({ systemState, coherence, stateLabel, primaryMessage }) {
  return (
    <article className={`system-body-orb-panel system-body-orb-panel--${systemState}`}>
      <div className="system-body-orb-panel__stage">
        <HealthOrb systemState={systemState} intensity={1 - coherence} />
      </div>
      <span>Facility condition</span>
      <strong>{stateLabel}</strong>
      <p>{primaryMessage}</p>
    </article>
  );
}
