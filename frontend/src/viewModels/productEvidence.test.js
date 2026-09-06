import { describe, expect, it } from "vitest";
import consequence from "../../tests/fixtures/measurable-consequence.json";
import { productEvidence } from "./productEvidence";

describe("historical attribution product projection", () => {
  it.each([
    "attribution_confidence", "attributionConfidence", "causal_evidence", "causalEvidence",
    "driver_attribution", "driverAttribution", "cause_attribution", "causeAttribution",
  ])("omits %s without changing recorded evidence", (field) => {
    const legacy = {
      findings: [{
        nested: { [field]: { conclusion: "LEGACY_ATTRIBUTION" } },
        relationships: [{ id: "water:load", correlation_delta: 0.7 }],
        measurable_consequence: consequence,
        provenance: { result_hash: "historical-result-hash" },
      }],
    };
    const saved = structuredClone(legacy);
    const projected = productEvidence(legacy).findings[0];
    expect(projected.nested).toEqual({});
    expect(projected.relationships).toEqual(saved.findings[0].relationships);
    expect(projected.measurable_consequence).toEqual(consequence);
    expect(projected.provenance).toEqual(saved.findings[0].provenance);
    expect(legacy).toEqual(saved);
  });
});
