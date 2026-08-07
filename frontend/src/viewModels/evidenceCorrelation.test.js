import { describe, expect, it } from "vitest";
import { CORRELATION_NON_CLAIM, buildCorrelationPresentation, describeRelationship } from "./evidenceCorrelation";

describe("evidence correlation presentation", () => {
  it("presents an evidence-safe empty state", () => {
    const presentation = buildCorrelationPresentation({
      correlation_status: "no_supported_relationship",
      related_packages: [],
      limitations: ["no_relationship_anchor"],
    }, { packageId: "package-a" });

    expect(presentation.title).toBe("No supported related findings");
    expect(presentation.items).toEqual([]);
    expect(presentation.limitations[0]).toMatch(/No supported temporal/);
    expect(presentation.nonClaim).toBe(CORRELATION_NON_CLAIM);
  });

  it("explains only persisted dimensions and evidence limitations", () => {
    const presentation = buildCorrelationPresentation({
      correlation_status: "related_packages_found",
      limitations: [],
      related_packages: [{
        relationship_id: "relationship-1",
        package_id: "package-b",
        strongest_supported_relationship: "overlapping_observation_window",
        supporting_relationships: ["overlapping_observation_window", "compatible_operating_context", "same_system"],
        evidence_refs: ["evidence-package:package-a#operating_context.comparison_window.start"],
        limitations: ["canonical_signal_identity_unavailable"],
      }],
    }, { packageId: "package-a" });

    expect(presentation.items[0].reason).toMatch(/overlapping observation windows/);
    expect(presentation.items[0].relationshipLabels).toEqual([
      "Overlapping observation window",
      "Compatible operating context",
      "Same persisted system",
    ]);
    expect(presentation.items[0].limitationLabels[0]).toMatch(/Canonical signal identity/);
  });

  it("does not turn analytical-pattern identity into a causal statement", () => {
    const description = describeRelationship({ strongest_supported_relationship: "related_analytical_pattern" });
    expect(description).toMatch(/explicit persisted analytical-pattern identifier/);
    expect(description).not.toMatch(/root cause|propagated|downstream|diagnosis/i);
  });
});
