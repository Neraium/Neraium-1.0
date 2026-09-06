/* @vitest-environment jsdom */
import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DiagnosticsPanel from "./DiagnosticsPanel";

afterEach(cleanup);

function renderPanel(siiIntelligence, result = {}) {
  const apiFetch = vi.fn(async () => ({
    ok: true,
    json: async () => ({ timeline: [] }),
  }));
  render(React.createElement(DiagnosticsPanel, {
    latestUploadResult: {
      job_id: "upload-1",
      ...result,
      sii_intelligence: {
        facility_state: "Stable",
        urgency: "nominal",
        confidence_basis: "Evidence remains within the learned range.",
        ...siiIntelligence,
      },
    },
    latestUploadSnapshot: null,
    hasActiveSession: true,
    hasCurrentUploadResult: true,
    hasResumedSession: false,
    apiFetch,
    accessCode: "",
    uploadStateView: { deriveTimeCoverage: () => ({ summary: "Recorded window" }) },
    uploadHistoryRows: [],
  }));
  return apiFetch;
}

describe("DiagnosticsPanel authority projection", () => {
  it("does not render historical attribution or renamed driver fields", async () => {
    const apiFetch = renderPanel({
      attribution_confidence: "LEGACY_ATTRIBUTION",
      causal_evidence: "LEGACY_CAUSAL_EVIDENCE",
      primary_driver: "LEGACY_PRIMARY_DRIVER",
      rooms: [{
        room: "Recorded segment",
        driver_category: "LEGACY_DRIVER_CATEGORY",
        attribution_confidence: "LEGACY_ROOM_ATTRIBUTION",
        confidence_components: { relationship_support: "high", persistence: "persistent" },
      }],
    }, { driver_attribution: { severity: "LEGACY_ATTRIBUTION_SEVERITY" } });
    expect(document.body.textContent).not.toContain("LEGACY_");
    expect(screen.queryByText("Attribution")).toBeNull();
    expect(screen.queryByText("Driver Category")).toBeNull();
    expect(screen.getByText("Recorded segment")).toBeTruthy();
    expect(screen.getByText("Relationship Support")).toBeTruthy();
    expect(screen.getByText("Persistent")).toBeTruthy();
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
  });

  it("uses only non-predictive review-window fields", async () => {
    const apiFetch = renderPanel({
      projected_time_to_failure: "Predicted failure in 8 hours",
      review_window: "Review during the next operating cycle",
    });

    expect(screen.getAllByText("Operational review window").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Review during the next operating cycle").length).toBeGreaterThan(0);
    expect(screen.queryByText("Predicted failure in 8 hours")).toBeNull();
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
  });

  it("does not reconstruct a review window from the removed prediction alias", async () => {
    const apiFetch = renderPanel({
      projected_time_to_failure: "Predicted failure in 8 hours",
    });

    expect(screen.queryByText("Predicted failure in 8 hours")).toBeNull();
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
  });
});
