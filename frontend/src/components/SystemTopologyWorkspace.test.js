import { describe, expect, it } from "vitest";
import { derivePrimaryMessage, deriveUploadSignal, deriveCurrentOutput } from "./SystemTopologyWorkspace";

describe("SystemTopologyWorkspace operator trust mapping", () => {
  it("keeps upload state pending when operator review evidence is not ready", () => {
    expect(deriveUploadSignal({
      operating_state: "stable",
      sii_intelligence: { facility_state: "stable" },
    }, { reviewReady: false })).toEqual({
      systemState: "unknown",
      label: "Telemetry still processing",
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

  it("does not reconstruct production governance from removed structural-facade fields", () => {
    const legacyGovernance = { gate_outcome: "PASS", admitted_state: "ALERT" };

    expect(deriveCurrentOutput({
      sourceIntelligence: { distributed_cognition_governance: legacyGovernance },
      distributed_cognition_governance: legacyGovernance,
    }, { awaitingSii: false }).detail).toBeNull();

    const aletheiaGate = { gate_outcome: "PASS", admitted_state: "WATCH" };
    expect(deriveCurrentOutput({
      sourceIntelligence: { aletheia_gate: aletheiaGate },
    }, { awaitingSii: false }).detail).toBeNull();
  });
});

 it("shows canonical evidence regardless of legacy denial", () => {
   const canonicalFinding = { exists: true, summary: "Current relationship evidence" };
   const output = deriveCurrentOutput({ canonicalFinding, sourceIntelligence: {
     aletheia_gate: { gate_outcome: "NO_PASS", admitted_state: "NONE" },
   } }, { awaitingSii: false });
   expect(output.hasFinding).toBe(true);
   expect(derivePrimaryMessage({ awaitingSii: false, pendingVerification: false,
     canonicalFinding, uploadSignal: {} })).toBe(canonicalFinding.summary);
 });
