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

export const FINGERPRINT_RIDGES = [
  { id: "hvac-outer-a", system: "hvac", path: "M17 74C17 42 38 18 64 18C78 18 88 28 88 42C88 52 82 58 73 58H66" },
  { id: "hvac-outer-b", system: "hvac", path: "M24 82C16 62 22 35 42 23C57 14 78 20 85 36C90 48 84 66 69 73C58 78 45 76 37 68" },
  { id: "flow-upper-a", system: "flow-pressure", path: "M27 36H42C52 36 59 43 59 52V66C59 73 64 78 71 78H81" },
  { id: "flow-upper-b", system: "flow-pressure", path: "M31 46C36 30 55 24 69 33C79 39 82 52C76 62 69 72 57 72H49" },
  { id: "pumping-left-a", system: "pumping", path: "M21 63C21 43 36 27 55 27C67 27 77 35 80 46C82 56 77 67 67 72C57 77 44 74 38 65" },
  { id: "pumping-left-b", system: "pumping", path: "M28 70V56C28 44 37 35 49 35H66C72 35 77 40 77 46V52" },
  { id: "electrical-core-a", system: "electrical", path: "M39 54C39 47 44 42 51 42C58 42 63 47 63 54C63 61 58 66 51 66C44 66 39 61 39 54Z" },
  { id: "electrical-core-b", system: "electrical", path: "M51 30V42M51 66V80M34 54H39M63 54H78" },
  { id: "water-lower-a", system: "water-quality", path: "M34 82C46 89 65 86 76 74C87 62 87 43 76 31" },
  { id: "water-lower-b", system: "water-quality", path: "M40 75C50 81 65 78 72 68C79 57 76 43 65 37" },
  { id: "flow-upper-c", system: "flow-pressure", path: "M38 27H58C73 27 84 38 84 53V55" },
  { id: "pumping-left-c", system: "pumping", path: "M32 57C35 47 43 42 52 42C61 42 68 49 68 58C68 67 61 74 52 74H45" },
  { id: "water-lower-c", system: "water-quality", path: "M44 87H58C75 87 89 73 89 56V48" },
  { id: "hvac-outer-c", system: "hvac", path: "M14 50C14 27 33 9 57 9C73 9 88 18 94 32" },
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

export function normalizeRidgeFamily(value) {
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
