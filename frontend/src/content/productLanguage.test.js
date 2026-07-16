import { describe, expect, it } from "vitest";
import { ANALYSIS_STATUS_LABELS, CONNECTOR_HEALTH_LABELS, INSIGHT_SEVERITY_LABELS, INTELLIGENCE_NAME, INTELLIGENCE_SHORT_NAME, PRODUCT_DESCRIPTOR, PRODUCT_NAME, connectorHealthLabel } from "./productLanguage";

describe("Neraium product language", () => {
  it("keeps the platform and its intelligence distinct", () => {
    expect(PRODUCT_NAME).toBe("Neraium");
    expect(INTELLIGENCE_NAME).toBe("Systemic Infrastructure Intelligence");
    expect(INTELLIGENCE_SHORT_NAME).toBe("SII");
    expect(PRODUCT_DESCRIPTOR).toBe("Systemic Infrastructure Intelligence (SII)");
  });

  it("uses approved severity, connector health, and analysis status labels", () => {
    expect(INSIGHT_SEVERITY_LABELS).toEqual(["Critical", "High", "Moderate", "Low"]);
    expect(CONNECTOR_HEALTH_LABELS).toEqual({ ready: "Healthy", degraded: "Degraded", offline: "Offline", not_configured: "Not configured" });
    expect(connectorHealthLabel("ready")).toBe("Healthy");
    expect(connectorHealthLabel("unknown")).toBe("Not configured");
    expect(ANALYSIS_STATUS_LABELS).toMatchObject({ queued: "Queued", processing: "Analyzing", saving_results: "Saving results", complete: "Complete", failed: "Failed" });
  });
});
