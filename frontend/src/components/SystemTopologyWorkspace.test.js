import { describe, expect, it } from "vitest";
import { deriveUploadSignal } from "./SystemTopologyWorkspace";

describe("SystemTopologyWorkspace operator trust mapping", () => {
  it("keeps upload state pending when operator review evidence is not ready", () => {
    expect(deriveUploadSignal({
      operating_state: "stable",
      sii_intelligence: { facility_state: "stable" },
    }, { reviewReady: false })).toEqual({
      systemState: "unknown",
      label: "Analysis pending verification",
      statusLight: "gray",
    });
  });

  it("maps drift evidence to needs review once operator review is ready", () => {
    expect(deriveUploadSignal({
      operating_state: "drift",
      drift_status: "elevated",
    }, { reviewReady: true })).toEqual({
      systemState: "watching",
      label: "Needs review",
      statusLight: "gray",
    });
  });
});
