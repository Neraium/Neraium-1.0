import { FINGERPRINT_RIDGES, resolveChangedFamilies } from "./OperationalOrb";

function normalizeStatus(status, state, tone) {
  const value = String(status ?? state?.status ?? state?.tone ?? tone ?? "").toLowerCase();
  if (["critical", "severe"].includes(value)) return "critical";
  if (["elevated", "risk", "high"].includes(value)) return "elevated";
  if (["warning", "drift", "behavior-change", "changed", "investigate"].includes(value)) return "warning";
  if (["learning", "analyzing", "building"].includes(value)) return "learning";
  if (["awaiting", "no-data", "ready", "neutral", "unknown"].includes(value)) return "awaiting";
  return "healthy";
}

export default function FacilityFingerprintMark({ className = "", state, status, tone, label = "Facility operational fingerprint" }) {
  const resolvedStatus = normalizeStatus(status, state, tone);
  const changedFamilies = resolveChangedFamilies({ state, hotspots: state?.hotspots, status: resolvedStatus });
  const classNames = [
    "facility-fingerprint-mark",
    "facility-fingerprint-mark--" + resolvedStatus,
    className,
  ].filter(Boolean).join(" ");

  return (
    <span className={classNames} role="img" aria-label={label} data-status={resolvedStatus}>
      <svg viewBox="0 0 100 100" aria-hidden="true" focusable="false">
        {FINGERPRINT_RIDGES.map((ridge) => (
          <path
            className={changedFamilies.has(ridge.system) ? "is-changed" : undefined}
            d={ridge.path}
            data-system={ridge.system}
            key={ridge.id}
            pathLength="1"
          />
        ))}
      </svg>
    </span>
  );
}
