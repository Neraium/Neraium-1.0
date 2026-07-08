export default function OperationalOrb({ state }) {
  return (
    <div className={`operational-orb operational-orb--${state.key}`} data-testid="operational-orb" aria-label={`Operational Fingerprint: ${state.label}`}>
      <div className="operational-orb__core" />
      <div className="operational-orb__ring" />
      <span>{state.label}</span>
    </div>
  );
}
