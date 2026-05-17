export const EMPTY_VALUE = "—";

const EMPTY_STRINGS = new Set([
  "",
  "awaiting telemetry",
  "awaiting uploaded telemetry",
  "baseline pending",
  "not assessed",
  "unavailable",
  "no active session",
  "pending activation",
  "pending",
  "n/a",
  "na",
  "none",
  "not connected",
  "not produced",
]);

export function isEffectivelyEmptyValue(value) {
  if (value === null || value === undefined) return true;
  if (typeof value === "number") return Number.isNaN(value);
  const text = String(value).trim().toLowerCase();
  if (!text) return true;
  if (EMPTY_STRINGS.has(text)) return true;
  if (text.includes("no active session")) return true;
  if (text.includes("awaiting telemetry")) return true;
  if (text.includes("awaiting uploaded telemetry")) return true;
  if (text.includes("pending activation")) return true;
  if (text.includes("not assessed")) return true;
  if (text.includes("unavailable")) return true;
  return false;
}

export function formatEmptyValue(value) {
  return isEffectivelyEmptyValue(value) ? EMPTY_VALUE : value;
}
