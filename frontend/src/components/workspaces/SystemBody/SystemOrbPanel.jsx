import HealthOrb from "../../HealthOrb";
import HeroPanel from "../../layout/HeroPanel";

export default function SystemOrbPanel({ systemState, coherence, stateLabel, primaryMessage }) {
  return (
    <HeroPanel className={`system-body-orb-panel system-body-orb-panel--${systemState}`}>
      <div className="system-body-orb-panel__stage">
        <HealthOrb systemState={systemState} intensity={1 - coherence} />
      </div>
      <span>Facility condition</span>
      <strong>{stateLabel}</strong>
      <p>{primaryMessage}</p>
    </HeroPanel>
  );
}
