const ORB_STATUS = {
  awaiting: {
    label: "Awaiting Operational Fingerprint",
    visualLabel: "Operational Status",
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
    label: "Investigation Recommended",
    visualLabel: "Operational Fingerprint",
    particleCount: 8,
  },
  elevated: {
    label: "Operational Changes Detected",
    visualLabel: "Operational Fingerprint",
    particleCount: 9,
  },
  critical: {
    label: "Immediate Investigation Recommended",
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

const FINGERPRINT_RIDGES = [
  "M50 19c-11 0-20 8-21 19-.4 7 4 12 11 13 8 1 14-4 14-11 0-5-4-9-9-9-4 0-7 3-7 7 0 3 2 5 5 5",
  "M39 72c-12-5-20-17-18-31 2-16 15-28 31-27 18 1 31 16 30 34-.6 14-9 26-22 31",
  "M28 62c-7-8-10-17-9-27 2-18 17-32 35-31 20 1 36 18 35 39-.5 11-5 21-13 29",
  "M36 41c.4-8 7-15 15-15 9 0 16 7 16 16 0 10-8 18-18 18-8 0-15-5-18-12",
  "M45 86c14-4 25-15 29-29 4-15-3-30-16-37-9-5-20-4-28 2",
  "M24 79c-10-11-15-25-13-40 3-23 22-40 45-39 26 2 46 24 44 50-.9 18-10 34-25 43",
  "M50 38c4 0 7 3 7 7 0 5-4 9-9 9-4 0-8-2-10-5",
];

function normalizeStatus(status, state) {
  const value = String(status ?? state?.status ?? state?.tone ?? state?.key ?? "").toLowerCase();
  if (["awaiting", "no-data", "ready", "neutral"].includes(value)) return "awaiting";
  if (["learning", "analyzing", "building"].includes(value)) return "learning";
  if (["healthy", "active", "monitoring", "stable"].includes(value)) return "healthy";
  if (["critical", "severe"].includes(value)) return "critical";
  if (["elevated", "risk", "high"].includes(value)) return "elevated";
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

function resolveRidgeCount(state, status, hotspotCount) {
  const relationshipCount = Number(state?.relationshipCount ?? state?.relationships?.length ?? state?.relationship_count);
  const explicit = Number(state?.ridgeCount ?? state?.fingerprintRidgeCount ?? state?.fingerprint_ridge_count);
  const count = Number.isFinite(explicit) ? explicit : Number.isFinite(relationshipCount) ? relationshipCount + 3 : hotspotCount + 4;
  const minimum = status === "awaiting" ? 2 : status === "learning" ? 4 : 5;
  return Math.max(minimum, Math.min(Math.round(count), FINGERPRINT_RIDGES.length));
}

export default function OperationalOrb({ state, status, hotspotCount, hotspots }) {
  const resolvedStatus = normalizeStatus(status, state);
  const config = ORB_STATUS[resolvedStatus];
  const resolvedHotspotCount = clampHotspotCount(hotspotCount ?? state?.hotspotCount, resolvedStatus);
  const resolvedHotspots = resolveHotspots({ hotspots: hotspots ?? state?.hotspots, hotspotCount: resolvedHotspotCount });
  const ridgeCount = resolveRidgeCount(state, resolvedStatus, resolvedHotspotCount);
  const particles = Array.from({ length: config.particleCount }, (_, index) => index);
  const label = state?.label ?? config.label;
  const visualLabel = state?.visualLabel ?? config.visualLabel;

  return (
    <div
      className={`operational-orb operational-orb--${resolvedStatus}`}
      data-testid="operational-orb"
      data-status={resolvedStatus}
      aria-label={`Operational status: ${label}`}
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
          <svg viewBox="0 0 100 100" aria-hidden="true" focusable="false">
            {FINGERPRINT_RIDGES.map((ridge, index) => (
              <path
                className={index < ridgeCount ? "is-active" : undefined}
                d={ridge}
                key={ridge}
                style={{ "--ridge-index": index }}
              />
            ))}
          </svg>
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
