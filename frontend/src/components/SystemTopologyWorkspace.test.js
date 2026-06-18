import { describe, expect, it } from "vitest";
import { derivePrimaryMessage, deriveUploadSignal } from "./SystemTopologyWorkspace";

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

  it("uses the canonical finding summary when analysis is present without a governed pass", () => {
    expect(derivePrimaryMessage({
      awaitingSii: false,
      pendingVerification: false,
      governed: { hasPass: false, passedFindingSummary: "" },
      canonicalFinding: { exists: true, summary: "Relationship drift detected across chilled water supply." },
      uploadSignal: { label: "Needs review" },
    })).toBe("Relationship drift detected across chilled water supply.");
  });
});
