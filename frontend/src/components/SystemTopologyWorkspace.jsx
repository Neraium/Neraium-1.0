import HealthOrb from "./HealthOrb";

const STATE = {
  nominal: {
    label: "Stable structure",
    description: "Core system relationships are holding steady across the facility.",
  },
  review: {
    label: "Relationship drift",
    description: "The structure is still intact, but system relationships are starting to pull out of alignment.",
  },
  elevated: {
    label: "Structural separation",
    description: "Facility systems are fragmenting and need attention before signal thresholds fail harder.",
  },
  unstable: {
    label: "Structural separation",
    description: "Facility systems are fragmenting and need attention before signal thresholds fail harder.",
  },
  info: {
    label: "Awaiting baseline",
    description: "Connect telemetry or upload a baseline source to activate live structural health.",
  },
};

export default function SystemTopologyWorkspace({ liveOps, selectedTarget, onSelectTarget }) {
  const state = STATE[liveOps.facilityTone] ?? STATE.info;
  const coherence = useMemo(() => {
    const total = (liveOps.relationshipRows ?? []).reduce((sum, row) => sum + Math.abs(Number(row.pair_weight ?? row.change ?? 0)), 0);
    return Math.max(0, Math.min(1, 1 - total));
  }, [liveOps.relationshipRows]);
  const systemState = liveOps.facilityTone === "nominal"
    ? "stable"
    : liveOps.facilityTone === "review"
      ? "drift"
      : "separation";
  const findings = liveOps.findings?.slice(0, 2) ?? [];
  const primaryMessage = findings[0]?.detail ?? state.description;
  const secondaryMessage = findings[1]?.detail ?? liveOps.heroSubline;
  const sourceLabel = liveOps.dataSourceLabel ?? "Awaiting data";
  const nextInspect = liveOps.primaryRoom ?? "No data connected yet";
  void selectedTarget;
  void onSelectTarget;

  return (
    <section className="system-body">
      <div className="system-body__header">
        <p className="system-body__kicker">System Body</p>
        <h2>System Health</h2>
        <p>{liveOps.heroSubline}</p>
      </div>

      <div className={`integrity-hero integrity-hero--solo integrity-hero--${systemState}`}>
        <div className="integrity-hero__score">
          <div className="integrity-hero__score-orb">
            <HealthOrb systemState={systemState} intensity={1 - coherence} />
          </div>
          <span>Facility condition</span>
          <strong>{state.label}</strong>
          <p>{primaryMessage}</p>
        </div>

        <div className="integrity-hero__meta">
          <div className="integrity-hero__summary">
            <p className="integrity-hero__kicker">System summary</p>
            <h3>{state.description}</h3>
            <p>{secondaryMessage}</p>
          </div>

          <div className="integrity-hero__metrics">
            <article className="integrity-hero__metric">
              <span>Data source</span>
              <strong>{sourceLabel}</strong>
            </article>
            <article className="integrity-hero__metric">
              <span>Primary room</span>
              <strong>{nextInspect}</strong>
            </article>
            <article className="integrity-hero__metric">
              <span>Latest upload</span>
              <strong>{liveOps.connectionSummary}</strong>
            </article>
            <article className="integrity-hero__metric">
              <span>What changed</span>
              <strong>{findings[0]?.title ?? "No active evidence yet"}</strong>
            </article>
          </div>
        </div>
      </div>
    </section>
  );
}

