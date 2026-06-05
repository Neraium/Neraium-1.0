export const NO_DATA_LABEL = "Awaiting uploaded telemetry";
export const AWAITING_TELEMETRY_LABEL = "Awaiting uploaded telemetry";

export function noDataGuidance() {
  return "Connect a live telemetry source or upload a multivariate telemetry file to activate structural observations.";
}

export function emptyConnectionLabel() {
  return NO_DATA_LABEL;
}
