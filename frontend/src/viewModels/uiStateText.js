export const NO_DATA_LABEL = "No data connected yet";
export const AWAITING_TELEMETRY_LABEL = "Awaiting telemetry";

export function noDataGuidance() {
  return "Connect live telemetry or upload a telemetry file to activate room context";
}

export function emptyConnectionLabel() {
  return NO_DATA_LABEL;
}
