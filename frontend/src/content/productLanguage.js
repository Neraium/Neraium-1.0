export const PRODUCT_NAME = "Neraium";
export const INTELLIGENCE_NAME = "Systemic Infrastructure Intelligence";
export const INTELLIGENCE_SHORT_NAME = "SII";
export const PRODUCT_DESCRIPTOR = `${INTELLIGENCE_NAME} (${INTELLIGENCE_SHORT_NAME})`;

export const INSIGHT_SEVERITY_LABELS = Object.freeze(["Critical", "High", "Moderate", "Low"]);
export const CONNECTOR_HEALTH_LABELS = Object.freeze({
  ready: "Healthy",
  degraded: "Degraded",
  offline: "Offline",
  not_configured: "Not configured",
});
export const ANALYSIS_STATUS_LABELS = Object.freeze({
  queued: "Queued",
  processing: "Analyzing",
  saving_results: "Saving results",
  complete: "Complete",
  failed: "Failed",
  cancelled: "Cancelled",
  timeout: "Timed out",
});

export function connectorHealthLabel(value) {
  const key = String(value ?? "not_configured").trim().toLowerCase();
  return CONNECTOR_HEALTH_LABELS[key] ?? "Not configured";
}
