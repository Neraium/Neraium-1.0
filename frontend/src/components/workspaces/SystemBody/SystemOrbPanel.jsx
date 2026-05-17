import HealthOrb from "../../HealthOrb";
import { EMPTY_VALUE } from "../../../viewModels/emptyValue";

const STATE_COPY = {
  stable: {
    code: "STABLE",
    attention: "Low attention",
    structural: "Relationships within baseline",
    telemetry: "Baseline telemetry aligned",
    progression: "No elevated drift persistence",
    environment: "Envelope steady",
  },
  watching: {
    code: "WATCH",
    attention: "Planned attention",
    structural: "Early relational drift",
    telemetry: "Telemetry consistency changing",
    progression: "Persistence under review",
    environment: "Directional variance",
  },
  drift: {
    code: "ALERT",
    attention: "Operator attention",
    structural: "Relational instability detected",
    telemetry: "Baseline divergence sustained",
    progression: "Deviation persistence increasing",
    environment: "Instability vector",
  },
  propagation_active: {
    code: "ALERT",
    attention: "Immediate review",
    structural: "Cross-subsystem spread observed",
    telemetry: "Multi-signal deviation corroborated",
    progression: "Progression rate elevated",
    environment: "Multi-zone coupling",
  },
  recovery: {
    code: "RECOVERING",
    attention: "Verify cooling",
    structural: "Relational recovery observed",
    telemetry: "Baseline re-alignment increasing",
    progression: "Deviation persistence decreasing",
    environment: "Envelope cooling",
  },
  unknown: {
    code: EMPTY_VALUE,
    attention: EMPTY_VALUE,
    structural: EMPTY_VALUE,
    telemetry: EMPTY_VALUE,
    progression: EMPTY_VALUE,
    environment: EMPTY_VALUE,
  },
  neutral: {
    code: EMPTY_VALUE,
    attention: EMPTY_VALUE,
    structural: EMPTY_VALUE,
    telemetry: EMPTY_VALUE,
    progression: EMPTY_VALUE,
    environment: EMPTY_VALUE,
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
  const resolvedLabel = stateLabel || EMPTY_VALUE;
  const copy = STATE_COPY[resolvedSystemState] ?? STATE_COPY.unknown;
  const instability = Math.max(0, Math.min(1, 1 - resolvedCoherence));
  const instabilityDisplay = resolvedSystemState === "unknown" ? EMPTY_VALUE : `${Math.round(instability * 100)}%`;
  const normalizedFocus = focusLabel || EMPTY_VALUE;
  void normalizedFocus;

  return (
    <aside
      className={`system-body-orb-panel system-body-orb-panel--${resolvedSystemState} ui-state-indicator ui-state-indicator--${resolvedUiState}`}
      aria-label="Primary infrastructure condition orb"
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
        <span className="section-label">Structural State</span>
        <strong>{copy.code}</strong>
        <em>{resolvedLabel}</em>
      </div>
      <div className="system-body-orb-panel__sync" aria-label="Live orb timestamp">
        <span />
        <strong>{lastUpdate || EMPTY_VALUE}</strong>
        <em>{resolvedSystemState === "unknown" ? EMPTY_VALUE : `Structural pressure ${instabilityDisplay}`}</em>
      </div>
    </aside>
  );
}
