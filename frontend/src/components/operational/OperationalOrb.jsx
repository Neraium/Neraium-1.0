const ORB_STATUS = {
  awaiting: {
    label: "Awaiting Operational Fingerprint",
    visualLabel: "Neraium",
    particleCount: 0,
  },
  learning: {
    label: "Building Operational Fingerprint",
    visualLabel: "Operational Fingerprint",
    particleCount: 14,
  },
  healthy: {
    label: "Operational Fingerprint Active",
    visualLabel: "Operational Fingerprint",
    particleCount: 8,
  },
  warning: {
    label: "Relationship Drift Detected",
    visualLabel: "Operational Fingerprint",
    particleCount: 8,
  },
  critical: {
    label: "Multiple High Severity Drift",
    visualLabel: "Operational Fingerprint",
    particleCount: 10,
  },
};

const DEFAULT_HOTSPOTS = [
  { x: 70, y: 34, scale: 1 },
  { x: 38, y: 66, scale: 0.84 },
  { x: 62, y: 70, scale: 1.12 },
  { x: 31, y: 39, scale: 0.76 },
  { x: 77, y: 57, scale: 0.92 },
];

function normalizeStatus(status, state) {
  const value = String(status ?? state?.status ?? state?.tone ?? state?.key ?? "").toLowerCase();
  if (["awaiting", "no-data", "ready", "neutral"].includes(value)) return "awaiting";
  if (["learning", "analyzing", "building"].includes(value)) return "learning";
  if (["healthy", "active", "monitoring", "stable"].includes(value)) return "healthy";
  if (["critical", "severe"].includes(value)) return "critical";
  if (["warning", "drift", "behavior-change", "changed", "investigate"].includes(value)) return "warning";
  return "awaiting";
}

function clampHotspotCount(value, status) {
  const fallback = status === "critical" ? 3 : status === "warning" ? 1 : 0;
  const count = Number(value ?? fallback);
  if (!Number.isFinite(count) || count <= 0) return 0;
  return Math.min(Math.round(count), DEFAULT_HOTSPOTS.length);
}

function resolveHotspots({ hotspots, hotspotCount }) {
  const positionedHotspots = Array.isArray(hotspots) ? hotspots : [];
  return Array.from({ length: hotspotCount }, (_, index) => {
    const fallback = DEFAULT_HOTSPOTS[index % DEFAULT_HOTSPOTS.length];
    const hotspot = positionedHotspots[index] ?? fallback;
    return {
      x: Number.isFinite(Number(hotspot.x)) ? Number(hotspot.x) : fallback.x,
      y: Number.isFinite(Number(hotspot.y)) ? Number(hotspot.y) : fallback.y,
      scale: Number.isFinite(Number(hotspot.scale)) ? Number(hotspot.scale) : fallback.scale,
      subsystem: hotspot.subsystem,
    };
  });
}

export default function OperationalOrb({ state, status, hotspotCount, hotspots }) {
  const resolvedStatus = normalizeStatus(status, state);
  const config = ORB_STATUS[resolvedStatus];
  const resolvedHotspotCount = clampHotspotCount(hotspotCount ?? state?.hotspotCount, resolvedStatus);
  const resolvedHotspots = resolveHotspots({ hotspots: hotspots ?? state?.hotspots, hotspotCount: resolvedHotspotCount });
  const particles = Array.from({ length: config.particleCount }, (_, index) => index);
  const label = state?.label ?? config.label;
  const visualLabel = state?.visualLabel ?? config.visualLabel;

  return (
    <div
      className={`operational-orb operational-orb--${resolvedStatus}`}
      data-testid="operational-orb"
      data-status={resolvedStatus}
      aria-label={`Operational Fingerprint: ${label}`}
    >
      <div className="operational-orb__glow" aria-hidden="true" />
      <div className="operational-orb__surface" aria-hidden="true">
        <div className="operational-orb__depth" />
        <div className="operational-orb__particle-field">
          {particles.map((particle) => (
            <i
              className="operational-orb__particle"
              key={particle}
              style={{
                "--particle-index": particle,
                "--particle-x": `${18 + ((particle * 23) % 64)}%`,
                "--particle-y": `${20 + ((particle * 31) % 58)}%`,
                "--particle-size": `${2 + (particle % 3)}px`,
                "--particle-delay": `${particle * -0.7}s`,
              }}
            />
          ))}
        </div>
        <div className="operational-orb__fingerprint">
          <i />
          <i />
          <i />
        </div>
        <div className="operational-orb__hotspots">
          {resolvedHotspots.map((hotspot, index) => (
            <i
              className="operational-orb__hotspot"
              key={`${hotspot.subsystem ?? "hotspot"}-${index}`}
              style={{
                "--hotspot-x": `${hotspot.x}%`,
                "--hotspot-y": `${hotspot.y}%`,
                "--hotspot-scale": hotspot.scale,
                "--hotspot-delay": `${index * -1.4}s`,
              }}
              title={hotspot.subsystem}
            />
          ))}
        </div>
        <div className="operational-orb__lens" />
        <div className="operational-orb__rim" />
      </div>
      <span>{visualLabel}</span>
    </div>
  );
}
