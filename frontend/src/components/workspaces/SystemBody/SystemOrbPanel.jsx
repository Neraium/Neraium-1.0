import SystemStateMark from "../../SystemStateMark";
import { EMPTY_VALUE } from "../../../viewModels/emptyValue";

const STATE_COPY = {
  stable: { code: "L1-L2", attention: "Stable / Monitoring" },
  watching: { code: "L3", attention: "Change Watch" },
  drift: { code: "L4-L5", attention: "System Behavior Changed" },
  propagation_active: { code: "L6-L7", attention: "Sustained Structural Shift" },
  recovery: { code: "RECOVERY", attention: "Stability Recovery" },
  unknown: { code: EMPTY_VALUE, attention: EMPTY_VALUE },
  neutral: { code: EMPTY_VALUE, attention: EMPTY_VALUE },
};

function normalizePanelState(systemState) {
  const value = String(systemState || "unknown").toLowerCase();
  if (value === "stable") return "stable";
  if (value === "watching" || value === "watch") return "watching";
  if (value === "drift" || value === "warning") return "drift";
  if (value === "propagation_active" || value === "critical" || value === "propagation" || value === "alert") return "propagation_active";
  if (value === "recovery" || value === "recovering") return "recovery";
  return "unknown";
}

export default function SystemOrbPanel({
  systemState,
  uiState,
  coherence,
  stateLabel,
  lastUpdate,
  focusLabel,
  orbData,
  compactPreview = false,
}) {
  const resolvedSystemState = normalizePanelState(systemState);
  const resolvedUiState = uiState || "neutral";
  const resolvedCoherence = Number.isFinite(coherence) ? coherence : 1;
  const resolvedLabel = stateLabel || EMPTY_VALUE;
  const copy = STATE_COPY[resolvedSystemState] ?? STATE_COPY.unknown;
  const instability = Math.max(0, Math.min(1, 1 - resolvedCoherence));
  const instabilityDisplay = resolvedSystemState === "unknown" ? EMPTY_VALUE : `${Math.round(instability * 100)}%`;
  const indicatorClass = compactPreview ? "" : `ui-state-indicator ui-state-indicator--${resolvedUiState}`;
  void focusLabel;

  return (
    <aside
      className={`system-body-orb-panel system-body-orb-panel--${resolvedSystemState} ${indicatorClass} ${compactPreview ? "system-body-orb-panel--compact-preview" : ""}`}
      aria-label={compactPreview ? "The Gate admitted condition indicator" : "System behavior intelligence field"}
    >
      <div className="system-body-orb-panel__lattice" aria-hidden="true">
        {Array.from({ length: 9 }, (_, index) => (
          <span key={index} style={{ "--lattice-index": index }} />
        ))}
      </div>
      <div className="system-body-orb-panel__halo system-body-orb-panel__halo--outer" />
      <div className="system-body-orb-panel__halo system-body-orb-panel__halo--inner" />
      <div className="system-body-orb-panel__depth" />
      <div className="system-body-orb-panel__ambient-motion" aria-hidden="true" />
      <div className="system-body-orb-panel__stage">
        <SystemStateMark
          systemState={resolvedSystemState}
          intensity={instability}
          animated
        />
      </div>
      {!compactPreview ? (
        <div className="system-body-orb-panel__meta">
          <span className="section-label">System Signal</span>
          <strong>{copy.code}</strong>
          <em>{resolvedLabel}</em>
        </div>
      ) : null}
      {!compactPreview ? (
        <div className="system-body-orb-panel__sync" aria-label="Live system mark timestamp">
          <span />
          <strong>{lastUpdate || EMPTY_VALUE}</strong>
          <em>{resolvedSystemState === "unknown" ? EMPTY_VALUE : `Change signal ${instabilityDisplay}`}</em>
        </div>
      ) : null}
      {!compactPreview && orbData ? (
        <div className="system-body-orb-panel__telemetry">
          <div><span className="section-label">Containment Boundary</span><strong>{orbData.containment ?? EMPTY_VALUE}</strong></div>
          <div><span className="section-label">Change Direction</span><strong>{orbData.propagationDirection ?? EMPTY_VALUE}</strong></div>
          <div><span className="section-label">Relationship Continuity</span><strong>{orbData.fragmentation ?? EMPTY_VALUE}</strong></div>
          <div><span className="section-label">Confidence</span><strong>{orbData.evidenceConfidence ?? EMPTY_VALUE}</strong></div>
        </div>
      ) : null}
    </aside>
  );
}
