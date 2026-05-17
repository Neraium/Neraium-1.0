export function classifyBaselineSeparation(value) {
  const v = Number(value);
  if (!Number.isFinite(v)) return "—";
  if (v < 1) return "Low";
  if (v < 3) return "Moderate";
  if (v < 6) return "Elevated";
  return "Severe";
}

export function classifyDriftVelocity(value) {
  const v = Number(value);
  if (!Number.isFinite(v)) return "—";
  if (v < 0) return "Recovering";
  if (v === 0) return "Stable";
  if (v < 1) return "Increasing";
  if (v < 3) return "Escalating";
  return "Rapidly escalating";
}

export function classifyDriftAcceleration(value) {
  const v = Number(value);
  if (!Number.isFinite(v)) return "—";
  if (v < 0) return "Decelerating";
  if (v === 0) return "Flat";
  if (v < 1) return "Increasing";
  if (v < 3) return "Accelerating";
  return "Rapidly accelerating";
}

export function formatStructuralRead(state) {
  const s = String(state ?? "").toLowerCase();
  if (!s) return "—";
  if (s.includes("stable")) return "Stable";
  if (s.includes("watch") || s.includes("review")) return "Needs Review";
  if (s.includes("alert") || s.includes("critical") || s.includes("unstable")) return "Alert";
  if (s.includes("recover")) return "Recovery";
  if (s.includes("pending")) return "Baseline Pending";
  return String(state);
}

export function formatTrajectorySignal(signal, hasUploadedTelemetry) {
  if (!hasUploadedTelemetry) return "—";
  if (!signal) return "Structural drift detected in uploaded telemetry";
  return "Structural drift detected in uploaded telemetry";
}
