import { useId } from "react";

const ORB_STATUS = {
  awaiting: {
    label: "Awaiting Operational Baseline",
    visualLabel: "Operational Status",
    particleCount: 0,
  },
  learning: {
    label: "Analyzing Operational Behavior",
    visualLabel: "Operational Status",
    particleCount: 16,
  },
  healthy: {
    label: "Healthy",
    visualLabel: "Operational Status",
    particleCount: 7,
  },
  warning: {
    label: "Investigation Recommended",
    visualLabel: "Operational Status",
    particleCount: 10,
  },
  elevated: {
    label: "Operational Changes Detected",
    visualLabel: "Operational Status",
    particleCount: 12,
  },
  critical: {
    label: "Critical",
    visualLabel: "Operational Status",
    particleCount: 14,
  },
};

const SYSTEM_HOTSPOT_POSITIONS = {
  "flow-pressure": { x: 70, y: 34, scale: 1, subsystem: "Flow & Pressure" },
  "water-quality": { x: 38, y: 66, scale: 0.84, subsystem: "Water Quality" },
  pumping: { x: 62, y: 70, scale: 1.12, subsystem: "Pumping System" },
  electrical: { x: 31, y: 39, scale: 0.76, subsystem: "Electrical" },
  hvac: { x: 77, y: 57, scale: 0.92, subsystem: "HVAC" },
};

export const FINGERPRINT_RIDGES = [
  { id: "core-loop", system: "electrical", confidence: 5, path: "M50 51C50 44 55 39 62 39C70 39 76 45 76 53C76 63 67 71 56 71C44 71 36 62 36 50C36 36 47 26 62 26C81 26 94 40 94 58" },
  { id: "core-return", system: "pumping", confidence: 2, path: "M58 50C58 55 54 59 49 59C44 59 40 55 40 50C40 42 47 36 56 35C67 34 78 42 79 54C80 69 67 82 51 82" },
  { id: "inner-left", system: "water-quality", confidence: 2, path: "M31 57C28 44 33 31 44 23C56 14 74 17 84 28C94 39 97 56 90 70C82 88 61 96 43 88" },
  { id: "inner-right", system: "flow-pressure", confidence: 3, path: "M45 75C55 81 69 78 78 68C87 58 87 43 78 33C70 24 57 21 46 26" },
  { id: "middle-left", system: "hvac", confidence: 3, path: "M24 68C17 47 23 26 40 14C57 2 82 7 96 25C109 42 111 66 100 85" },
  { id: "middle-return", system: "pumping", confidence: 4, path: "M36 88C52 101 78 97 94 80C110 62 109 34 92 18" },
  { id: "outer-left", system: "water-quality", confidence: 4, path: "M18 79C5 54 12 24 35 8C58 4 91 8 108 23C126 48 122 83 99 104" },
  { id: "outer-right", system: "flow-pressure", confidence: 5, path: "M31 97C52 116 88 111 108 88C127 67 128 34 111 11" },
  { id: "base-arc", system: "electrical", confidence: 5, path: "M42 105C56 112 74 111 88 102" },
  { id: "top-arc", system: "hvac", confidence: 5, path: "M41 18C55 9 75 10 89 21" },
];

const STATUS_FALLBACK_FAMILIES = {
  warning: ["water-quality"],
  elevated: ["pumping", "flow-pressure"],
  critical: ["electrical", "pumping", "water-quality"],
};

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

function clampHotspotCount(value) {
  if (value == null) return undefined;
  const count = Number(value);
  if (!Number.isFinite(count) || count <= 0) return 0;
  return Math.min(
    Math.round(count),
    Object.keys(SYSTEM_HOTSPOT_POSITIONS).length
  );
}

function resolveHotspots({ hotspots, hotspotCount, changedFamilies }) {
  const positionedHotspots = Array.isArray(hotspots) ? hotspots : [];
  const meaningfulHotspots = positionedHotspots
    .map((hotspot) => {
      const family = normalizeRidgeFamily(
        hotspot?.system
        ?? hotspot?.subsystem
        ?? hotspot?.label
        ?? hotspot?.name
        ?? hotspot?.relationship
      );
      const fallback = SYSTEM_HOTSPOT_POSITIONS[family];
      if (!fallback) return null;
      return {
        x: Number.isFinite(Number(hotspot.x))
          ? Number(hotspot.x)
          : fallback.x,
        y: Number.isFinite(Number(hotspot.y))
          ? Number(hotspot.y)
          : fallback.y,
        scale: Number.isFinite(Number(hotspot.scale))
          ? Number(hotspot.scale)
          : fallback.scale,
        subsystem:
          hotspot.subsystem
          ?? hotspot.label
          ?? fallback.subsystem,
        system: family,
      };
    })
    .filter(Boolean);
  if (hotspotCount === 0) return [];
  if (meaningfulHotspots.length) {
    return meaningfulHotspots.slice(
      0,
      hotspotCount ?? meaningfulHotspots.length
    );
  }
  return Array.from(changedFamilies)
    .map((family) => (
      SYSTEM_HOTSPOT_POSITIONS[family]
        ? {
            ...SYSTEM_HOTSPOT_POSITIONS[family],
            system: family,
          }
        : null
    ))
    .filter(Boolean)
    .slice(0, hotspotCount ?? changedFamilies.size);
}

function resolveRidgeCount(state, status, hotspotCount) {
  const relationshipCount = Number(state?.relationshipCount ?? state?.relationships?.length ?? state?.relationship_count);
  const explicit = Number(state?.ridgeCount ?? state?.fingerprintRidgeCount ?? state?.fingerprint_ridge_count);
  const resolvedHotspotCount = Number.isFinite(hotspotCount)
    ? hotspotCount
    : 0;
  const count = Number.isFinite(explicit)
    ? explicit
    : Number.isFinite(relationshipCount)
      ? relationshipCount + 5
      : resolvedHotspotCount + 8;
  const minimum =
    status === "awaiting"
      ? 3
      : status === "learning"
        ? 0
        : 10;
  return Math.max(minimum, Math.min(Math.round(count), FINGERPRINT_RIDGES.length));
}

export function normalizeRidgeFamily(value) {
  const text = String(value ?? "").toLowerCase();
  if (!text) return "";
  if (/water|quality|chemical|chlor|dose|feed|ph|orp|conductivity|treatment/.test(text)) return "water-quality";
  if (/flow|pressure|filter|filtration|filtr|hydraulic|valve|differential|dp/.test(text)) return "flow-pressure";
  if (/pump|pumping|vfd|motor|circulation|recirculation/.test(text)) return "pumping";
  if (/hvac|thermal|cool|chill|tower|condenser|air|heat/.test(text)) return "hvac";
  if (/electric|electrical|power|panel|breaker|current|voltage|controls|control/.test(text)) return "electrical";
  return "";
}

function collectFamilyCandidates(value) {
  if (!value) return [];
  if (Array.isArray(value)) return value.flatMap(collectFamilyCandidates);
  if (typeof value === "object") {
    return [
      value.system,
      value.subsystem,
      value.label,
      value.name,
      value.type,
      value.metricName,
      value.summary,
      value.relationship,
    ].filter(Boolean);
  }
  return [value];
}

export function resolveChangedFamilies({ state, hotspots, status }) {
  const candidates = [
    ...collectFamilyCandidates(state?.ridgeActivity),
    ...collectFamilyCandidates(state?.systemFamilies),
    ...collectFamilyCandidates(state?.affectedSystems),
    ...collectFamilyCandidates(state?.changedSystems),
    ...collectFamilyCandidates(state?.systems),
    ...collectFamilyCandidates(state?.relationshipLabels),
    ...collectFamilyCandidates(hotspots),
  ];
  const families = new Set(candidates.map(normalizeRidgeFamily).filter(Boolean));
  if (families.size === 0) {
    (STATUS_FALLBACK_FAMILIES[status] ?? []).forEach((family) => families.add(family));
  }
  return families;
}

function isRidgeVisible(ridge, index, ridgeCount, changedFamilies, status) {
  if (changedFamilies.has(ridge.system)) return true;
  if (status === "awaiting") return ridge.confidence <= 2;
  if (status === "learning") return ridge.confidence <= 4;
  return index < ridgeCount;
}

export default function OperationalOrb({ state, status, hotspotCount, hotspots, minimal = false, hideVisualLabel = false }) {
  const instanceId = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const resolvedStatus = normalizeStatus(status, state);
  const config = ORB_STATUS[resolvedStatus];
  const explicitHotspots = hotspots ?? state?.hotspots;
  const changedFamilies = resolveChangedFamilies({ state, hotspots: explicitHotspots, status: resolvedStatus });
  const resolvedHotspotCount = clampHotspotCount(hotspotCount ?? state?.hotspotCount);
  const resolvedHotspots = resolveHotspots({ hotspots: explicitHotspots, hotspotCount: resolvedHotspotCount, changedFamilies });
  const ridgeCount = resolveRidgeCount(state, resolvedStatus, resolvedHotspotCount);
  const visibleRidges = FINGERPRINT_RIDGES.map((ridge, index) => ({
    ...ridge,
    index,
    active: isRidgeVisible(ridge, index, ridgeCount, changedFamilies, resolvedStatus),
    changed: changedFamilies.has(ridge.system),
  }));
  const motionRidges = visibleRidges.filter((ridge) => ridge.active && (ridge.changed || resolvedStatus === "healthy" || resolvedStatus === "learning"));
  const fallbackMotionRidges = visibleRidges.filter((ridge) => ridge.active);
  const particles = Array.from({ length: config.particleCount }, (_, index) => {
    const ridgePool = motionRidges.length ? motionRidges : fallbackMotionRidges;
    const ridge = ridgePool[index % Math.max(ridgePool.length, 1)] ?? visibleRidges[0];
    return { index, ridge };
  });
  const label = state?.label ?? config.label;
  const visualLabel = state?.visualLabel ?? config.visualLabel;
  const className = [
    "operational-orb",
    `operational-orb--${resolvedStatus}`,
    minimal ? "operational-orb--minimal" : "",
  ].filter(Boolean).join(" ");

  return (
    <div
      className={className}
      data-testid="operational-orb"
      data-status={resolvedStatus}
      role="img"
      aria-label={`Operational status: ${label}`}
    >
      <div className="operational-orb__glow" aria-hidden="true" />
      <div className="operational-orb__surface" aria-hidden="true">
        <div className="operational-orb__depth" />
        {!minimal ? <div className="operational-orb__particle-field" /> : null}
        {!minimal ? (
        <div className="operational-orb__fingerprint">
          <svg viewBox="0 0 100 100" aria-hidden="true" focusable="false">
            {visibleRidges.map((ridge) => (
              <path
                className={[
                  ridge.active ? "is-active" : "",
                  ridge.changed ? "is-changed" : "",
                ].filter(Boolean).join(" ") || undefined}
                d={ridge.path}
                data-system={ridge.system}
                id={`${instanceId}-${ridge.id}`}
                key={ridge.id}
                pathLength="1"
                style={{ "--ridge-index": ridge.index }}
              />
            ))}
            {particles.map(({ index, ridge }) => (
              <circle
                className="operational-orb__ridge-particle"
                data-system={ridge?.system}
                key={`${ridge?.id ?? "ridge"}-${index}`}
                r={resolvedStatus === "critical" ? "1.18" : "0.95"}
                style={{ "--ridge-particle-index": index }}
              >
                <animateMotion
                  begin={`${index * -0.62}s`}
                  dur={`${resolvedStatus === "warning" || resolvedStatus === "elevated" ? 4.8 : resolvedStatus === "critical" ? 6.6 : 7.8}s`}
                  repeatCount="indefinite"
                  rotate="auto"
                >
                  <mpath href={`#${instanceId}-${ridge?.id}`} />
                </animateMotion>
              </circle>
            ))}
          </svg>
        </div>
        ) : null}
        {!minimal ? (
        <div className="operational-orb__hotspots" aria-hidden="true">
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
            />
          ))}
        </div>
        ) : null}
        <div className="operational-orb__lens" />
        <div className="operational-orb__rim" />
      </div>
      {hideVisualLabel ? null : <span>{visualLabel}</span>}
    </div>
  );
}
