export function classifyBaselineSeparation(value) {
  const v = Number(value);
  if (!Number.isFinite(v)) return "-";
  if (v < 1) return "Low";
  if (v < 3) return "Moderate";
  if (v < 6) return "Elevated";
  return "Severe";
}

export function classifyDriftVelocity(value) {
  const v = Number(value);
  if (!Number.isFinite(v)) return "-";
  if (v < 0) return "Recovering";
  if (v === 0) return "Stable";
  if (v < 1) return "Increasing";
  if (v < 3) return "Escalating";
  return "Rapidly escalating";
}

export function classifyDriftAcceleration(value) {
  const v = Number(value);
  if (!Number.isFinite(v)) return "-";
  if (v < 0) return "Decelerating";
  if (v === 0) return "Flat";
  if (v < 1) return "Increasing";
  if (v < 3) return "Accelerating";
  return "Rapidly accelerating";
}

export function formatStructuralRead(state) {
  const s = String(state ?? "").toLowerCase();
  if (!s) return "-";
  if (s.includes("stable")) return "Stable";
  if (s.includes("watch") || s.includes("review")) return "Needs Review";
  if (s.includes("alert") || s.includes("critical") || s.includes("unstable")) return "Structural shift";
  if (s.includes("recover")) return "Recovery";
  if (s.includes("pending")) return "Baseline Pending";
  return String(state);
}

export function formatTrajectorySignal(signal, hasUploadedTelemetry) {
  if (!hasUploadedTelemetry) return "-";
  if (!signal) return "System behavior changed in uploaded telemetry";
  return "System behavior changed in uploaded telemetry";
}

export function mapStructuralSeverity(distance, velocity) {
  const d = Math.abs(Number(distance) || 0);
  const v = Number(velocity) || 0;
  if (d < 0.16 && Math.abs(v) < 0.015) return "Stable baseline";
  if (d < 0.36 && Math.abs(v) < 0.03) return "Minor deviation emerging";
  if (d < 0.7 || v >= 0.03) return "System behavior change increasing";
  if (d < 1.1) return "Persistent instability detected";
  return "Structural shift accelerating";
}

export function mapStructuralInterpretation(distance, velocity, acceleration) {
  const d = Math.abs(Number(distance) || 0);
  const v = Number(velocity) || 0;
  const a = Number(acceleration) || 0;
  if (d < 0.16 && Math.abs(v) < 0.015) return "System behavior remains close to baseline.";
  if (v < 0) return "Separation is easing and trending toward stability.";
  if (a > 0.03) return "Deviation rate is accelerating across recent windows.";
  if (v > 0.02) return "Deviation is expanding and should be monitored closely.";
  return "Instability progression remains active.";
}
