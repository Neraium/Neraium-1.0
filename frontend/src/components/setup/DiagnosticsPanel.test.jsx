/* @vitest-environment jsdom */
import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DiagnosticsPanel from "./DiagnosticsPanel";

afterEach(cleanup);

function renderPanel(siiIntelligence) {
  const apiFetch = vi.fn(async () => ({
    ok: true,
    json: async () => ({ timeline: [] }),
  }));
  render(React.createElement(DiagnosticsPanel, {
    latestUploadResult: {
      job_id: "upload-1",
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
    uploadStateView: {},
    uploadHistoryRows: [],
  }));
  return apiFetch;
}

describe("DiagnosticsPanel authority projection", () => {
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
