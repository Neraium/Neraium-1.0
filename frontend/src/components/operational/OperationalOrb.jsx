import { useId } from "react";

const ORB_STATUS = {
  awaiting: {
    label: "Awaiting Operational Fingerprint",
    visualLabel: "Operational Status",
    particleCount: 0,
  },
  learning: {
    label: "Building Operational Fingerprint",
    visualLabel: "Operational Fingerprint",
    particleCount: 16,
  },
  healthy: {
    label: "Operational Fingerprint Active",
    visualLabel: "Operational Fingerprint",
    particleCount: 7,
  },
  warning: {
    label: "Investigation Recommended",
    visualLabel: "Operational Fingerprint",
    particleCount: 10,
  },
  elevated: {
    label: "Operational Changes Detected",
    visualLabel: "Operational Fingerprint",
    particleCount: 12,
  },
  critical: {
    label: "Immediate Investigation Recommended",
    visualLabel: "Operational Fingerprint",
    particleCount: 14,
  },
};

const DEFAULT_HOTSPOTS = [
  { x: 70, y: 34, scale: 1, subsystem: "Flow & Pressure" },
  { x: 38, y: 66, scale: 0.84, subsystem: "Water Quality" },
  { x: 62, y: 70, scale: 1.12, subsystem: "Pumping System" },
  { x: 31, y: 39, scale: 0.76, subsystem: "Electrical" },
  { x: 77, y: 57, scale: 0.92, subsystem: "HVAC" },
];

const FINGERPRINT_RIDGES = [
  { id: "hvac-outer-a", system: "hvac", path: "M18 73C8 55 11 30 28 14C44-1 70 1 85 18C99 35 100 61 87 79C74 97 45 101 28 86" },
  { id: "hvac-outer-b", system: "hvac", path: "M24 79C12 64 12 38 25 22C39 5 65 4 80 20C94 35 95 59 83 75C71 91 47 96 31 84" },
  { id: "flow-upper-a", system: "flow-pressure", path: "M26 38C31 21 48 12 64 18C78 23 87 37 85 52C84 64 78 74 68 80" },
  { id: "flow-upper-b", system: "flow-pressure", path: "M32 42C35 29 48 22 60 26C71 30 78 40 77 52C76 63 69 72 59 76" },
  { id: "pumping-left-a", system: "pumping", path: "M24 64C17 48 22 29 36 20C49 12 67 16 76 29C84 41 82 58 72 68C62 79 45 81 34 72" },
  { id: "pumping-left-b", system: "pumping", path: "M31 68C24 55 27 40 38 31C49 22 65 26 72 38C79 50 74 65 62 71C51 77 39 76 31 68" },
  { id: "electrical-core-a", system: "electrical", path: "M48 43C55 39 64 43 66 51C68 60 61 68 52 69C43 70 36 63 37 54C38 49 42 45 48 43" },
  { id: "electrical-core-b", system: "electrical", path: "M49 50C53 47 59 49 60 54C61 59 57 63 52 63C47 63 43 59 44 54C45 52 46 51 49 50" },
  { id: "water-lower-a", system: "water-quality", path: "M36 78C47 86 66 82 74 69C81 58 79 43 69 34C60 26 46 25 37 33" },
  { id: "water-lower-b", system: "water-quality", path: "M42 73C51 78 64 74 69 64C74 55 71 44 63 38C55 32 44 34 39 42" },
  { id: "flow-upper-c", system: "flow-pressure", path: "M38 31C48 21 66 25 73 37C81 50 75 68 62 74" },
  { id: "pumping-left-c", system: "pumping", path: "M30 56C28 46 33 36 42 32C52 28 63 33 66 43C70 54 63 65 52 67C44 69 36 65 32 59" },
  { id: "water-lower-c", system: "water-quality", path: "M47 82C62 83 76 74 81 60C86 46 81 31 69 23" },
  { id: "hvac-outer-c", system: "hvac", path: "M16 50C16 27 34 9 56 10C80 11 96 31 94 54" },
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
      subsystem: hotspot.subsystem ?? fallback.subsystem,
    };
  });
}

function resolveRidgeCount(state, status, hotspotCount) {
  const relationshipCount = Number(state?.relationshipCount ?? state?.relationships?.length ?? state?.relationship_count);
  const explicit = Number(state?.ridgeCount ?? state?.fingerprintRidgeCount ?? state?.fingerprint_ridge_count);
  const count = Number.isFinite(explicit) ? explicit : Number.isFinite(relationshipCount) ? relationshipCount + 5 : hotspotCount + 8;
  const minimum = status === "awaiting" ? 3 : status === "learning" ? 9 : 10;
  return Math.max(minimum, Math.min(Math.round(count), FINGERPRINT_RIDGES.length));
}

function normalizeRidgeFamily(value) {
  const text = String(value ?? "").toLowerCase();
  if (!text) return "";
  if (/water|quality|chemical|chlor|dose|feed|ph|orp|conductivity|treatment/.test(text)) return "water-quality";
  if (/flow|pressure|filter|hydraulic|valve|differential|dp/.test(text)) return "flow-pressure";
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

function resolveChangedFamilies({ state, hotspots, status }) {
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
  if (index < ridgeCount) return true;
  return status !== "awaiting" && changedFamilies.has(ridge.system);
}

export default function OperationalOrb({ state, status, hotspotCount, hotspots }) {
  const instanceId = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const resolvedStatus = normalizeStatus(status, state);
  const config = ORB_STATUS[resolvedStatus];
  const explicitHotspots = hotspots ?? state?.hotspots;
  const resolvedHotspotCount = clampHotspotCount(hotspotCount ?? state?.hotspotCount, resolvedStatus);
  const resolvedHotspots = resolveHotspots({ hotspots: explicitHotspots, hotspotCount: resolvedHotspotCount });
  const ridgeCount = resolveRidgeCount(state, resolvedStatus, resolvedHotspotCount);
  const changedFamilies = resolveChangedFamilies({ state, hotspots: explicitHotspots, status: resolvedStatus });
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
        <div className="operational-orb__particle-field" />
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
