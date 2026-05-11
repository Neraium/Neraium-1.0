import { useMemo } from "react";
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
  const primaryItem = liveOps.interventionItems?.[0] ?? null;
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
  const awaitingSii = liveOps.intelligenceMode === "empty" || liveOps.intelligenceMode === "processing";
  const awaitingLabel = liveOps.intelligenceMode === "processing" ? "SII analysis running" : "Awaiting SII analysis";
  const issueType = awaitingSii ? awaitingLabel : (primaryItem?.title ?? findings[0]?.title ?? liveOps.facilityStateLabel ?? state.label);
  const suspectedLocation = awaitingSii ? awaitingLabel : (primaryItem?.label ?? liveOps.primaryWindow?.label ?? "Location not isolated");
  const runway = awaitingSii ? awaitingLabel : (primaryItem?.projectedTimeToFailure ?? primaryItem?.window ?? liveOps.primaryWindow?.window ?? "Runway unavailable");
  const urgency = awaitingSii ? awaitingLabel : (primaryItem?.status ?? liveOps.primaryWindow?.status ?? state.label);
  const confidence = awaitingSii
    ? awaitingLabel
    : (Number.isFinite(primaryItem?.confidence) ? `${primaryItem.confidence}% evidence quality` : (liveOps.readinessLabel ?? "Evidence building"));
  const primaryEvidence = awaitingSii
    ? awaitingLabel
    : (primaryItem?.supportingEvidence?.[0] ?? findings[0]?.detail ?? "No active SII evidence yet");
  const relationshipEvidence = awaitingSii
    ? awaitingLabel
    : (primaryItem?.relationshipEvidence?.[0] ?? liveOps.relationshipRows?.[0]?.detail ?? "Relationship evidence not isolated yet");
  const lastUpdate = liveOps.connectionSummary ?? "No confirmed update";
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
              <span>Issue type</span>
              <strong>{issueType}</strong>
            </article>
            <article className="integrity-hero__metric">
              <span>Suspected location</span>
              <strong>{suspectedLocation}</strong>
            </article>
            <article className="integrity-hero__metric">
              <span>Operational runway</span>
              <strong>{runway}</strong>
            </article>
            <article className="integrity-hero__metric">
              <span>Urgency</span>
              <strong>{urgency}</strong>
            </article>
            <article className="integrity-hero__metric">
              <span>Evidence quality</span>
              <strong>{confidence}</strong>
            </article>
            <article className="integrity-hero__metric">
              <span>Latest update</span>
              <strong>{lastUpdate}</strong>
            </article>
          </div>

          <div className="integrity-hero__evidence">
            <article>
              <span>Primary evidence</span>
              <p>{primaryEvidence}</p>
            </article>
            <article>
              <span>Relationship evidence</span>
              <p>{relationshipEvidence}</p>
            </article>
            <article>
              <span>Source of truth</span>
              <p>{sourceLabel}. Operational conclusions remain backend/SII sourced.</p>
            </article>
          </div>
        </div>
      </div>
    </section>
  );
}

