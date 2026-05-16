import HealthOrb from "../../HealthOrb";

const STATE_COPY = {
  stable: {
    code: "STABLE",
    attention: "Low attention",
    structural: "Relationships holding",
    telemetry: "Continuous baseline lock",
    progression: "No active escalation",
    environment: "Envelope steady",
  },
  watching: {
    code: "WATCH",
    attention: "Planned attention",
    structural: "Minor drift forming",
    telemetry: "Telemetry coupled",
    progression: "Escalation watch",
    environment: "Directional variance",
  },
  drift: {
    code: "ALERT",
    attention: "Operator attention",
    structural: "Relationship separation",
    telemetry: "Pressure signal active",
    progression: "Severity increasing",
    environment: "Instability vector",
  },
  propagation_active: {
    code: "ALERT",
    attention: "Immediate review",
    structural: "Propagation active",
    telemetry: "Threshold signal active",
    progression: "Containment window",
    environment: "Multi-zone coupling",
  },
  recovery: {
    code: "RECOVERING",
    attention: "Verify cooling",
    structural: "Convergence forming",
    telemetry: "Stabilizing signal",
    progression: "Severity receding",
    environment: "Envelope cooling",
  },
  unknown: {
    code: "DISCONNECTED",
    attention: "Awaiting baseline",
    structural: "Structure unverified",
    telemetry: "Evidence stream pending",
    progression: "No escalation model",
    environment: "Dormant field",
  },
  neutral: {
    code: "DISCONNECTED",
    attention: "Awaiting baseline",
    structural: "Structure unverified",
    telemetry: "Evidence stream pending",
    progression: "No escalation model",
    environment: "Dormant field",
  },
};

function normalizePanelState(systemState) {
  const value = String(systemState || "unknown").toLowerCase();
  if (value === "stable") return "stable";
  if (value === "watching" || value === "watch") return "watching";
  if (value === "drift" || value === "warning") return "drift";
  if (value === "propagation_active" || value === "critical" || value === "propagation") return "propagation_active";
  if (value === "recovery" || value === "recovering") return "recovery";
  return "unknown";
}

export default function SystemOrbPanel({ systemState, uiState, coherence, stateLabel, lastUpdate, focusLabel }) {
  const resolvedSystemState = normalizePanelState(systemState);
  const resolvedUiState = uiState || "neutral";
  const resolvedCoherence = Number.isFinite(coherence) ? coherence : 1;
  const resolvedLabel = stateLabel || "Awaiting baseline";
  const copy = STATE_COPY[resolvedSystemState] ?? STATE_COPY.unknown;
  const instability = Math.max(0, Math.min(1, 1 - resolvedCoherence));
  const instabilityDisplay = `${Math.round(instability * 100)}%`;
  const normalizedFocus = focusLabel || "Facility envelope";

  return (
    <aside
      className={`system-body-orb-panel system-body-orb-panel--${resolvedSystemState} ui-state-indicator ui-state-indicator--${resolvedUiState}`}
      aria-label="Canonical facility condition orb"
    >
      <div className="system-body-orb-panel__lattice" aria-hidden="true">
        {Array.from({ length: 9 }, (_, index) => (
          <span key={index} style={{ "--lattice-index": index }} />
        ))}
      </div>
      <div className="system-body-orb-panel__halo system-body-orb-panel__halo--outer" />
      <div className="system-body-orb-panel__halo system-body-orb-panel__halo--inner" />
      <div className="system-body-orb-panel__depth" />
      <div className="system-body-orb-panel__stage">
        <HealthOrb systemState={resolvedSystemState} intensity={instability} />
      </div>
      <div className="system-body-orb-panel__meta">
        <span className="section-label">Canonical health instrument</span>
        <strong>{copy.code}</strong>
        <em>{resolvedLabel}</em>
      </div>
      <div className="system-body-orb-panel__telemetry" aria-label="Orb telemetry coupling state">
        <div>
          <span className="metadata-text">Focus</span>
          <strong>{normalizedFocus}</strong>
        </div>
        <div>
          <span className="metadata-text">Structural condition</span>
          <strong>{copy.structural}</strong>
        </div>
        <div>
          <span className="metadata-text">Telemetry state</span>
          <strong>{copy.telemetry}</strong>
        </div>
        <div>
          <span className="metadata-text">Progression severity</span>
          <strong>{copy.progression}</strong>
        </div>
        <div>
          <span className="metadata-text">Environmental stability</span>
          <strong>{copy.environment}</strong>
        </div>
        <div>
          <span className="metadata-text">Attention level</span>
          <strong>{copy.attention}</strong>
        </div>
      </div>
      <div className="system-body-orb-panel__sync" aria-label="Live orb timestamp">
        <span />
        <strong>{lastUpdate || "No confirmed update"}</strong>
        <em>Instability field {instabilityDisplay}</em>
      </div>
    </aside>
  );
}
