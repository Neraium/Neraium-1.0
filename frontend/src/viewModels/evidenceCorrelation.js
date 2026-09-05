const RELATIONSHIP_LABELS = Object.freeze({
  shared_canonical_signal: "Shared canonical signal",
  overlapping_observation_window: "Overlapping observation window",
  temporally_adjacent: "Adjacent observation window",
  related_analytical_pattern: "Related analytical pattern",
  compatible_operating_context: "Compatible operating context",
  same_system: "Same persisted system",
});

const LIMITATION_LABELS = Object.freeze({
  package_lifecycle_ineligible: "This record is not an eligible completed analytical package.",
  legacy_package_without_correlation_projection: "This package predates relationship projection.",
  missing_required_scope: "Required tenant, workspace, or system identity is unavailable.",
  observation_window_unavailable: "A supported observation window is unavailable.",
  operating_context_unavailable: "Comparable operating context is unavailable.",
  canonical_signal_identity_unavailable: "Canonical signal identity is unavailable.",
  analytical_pattern_identity_unavailable: "Analytical pattern identity is unavailable.",
  related_package_projection_missing: "A referenced related-package projection is unavailable.",
  stale_or_corrupt_correlation_sidecar: "Relationship evidence is stale or inconsistent and was excluded.",
  no_relationship_anchor: "No supported temporal, signal, or analytical-pattern anchor was persisted.",
});

export const CORRELATION_NON_CLAIM =
  "Related evidence describes recorded associations and their limits.";

export function relationshipLabel(value) {
  return RELATIONSHIP_LABELS[value] ?? "Supported package relationship";
}

export function limitationLabel(value) {
  return LIMITATION_LABELS[value] ?? "A relationship evidence dimension is unavailable.";
}

export function describeRelationship(relationship) {
  switch (relationship?.strongest_supported_relationship) {
    case "shared_canonical_signal":
      return "The packages use at least one shared canonical signal in the same persisted system.";
    case "overlapping_observation_window":
      return "The packages contain evidence from overlapping observation windows in the same persisted system.";
    case "temporally_adjacent":
      return "The packages contain evidence from adjacent observation windows in the same persisted system.";
    case "related_analytical_pattern":
      return "The packages share an explicit persisted analytical-pattern identifier in the same system.";
    default:
      return "A persisted evidence dimension relates these separate analytical packages.";
  }
}

export function buildCorrelationPresentation(payload, { loading = false, error = "", packageId = "" } = {}) {
  const base = { items: [], limitations: [], nonClaim: CORRELATION_NON_CLAIM, packageId };
  if (loading) return { ...base, tone: "loading", title: "Checking related findings", body: "Reading persisted relationship evidence." };
  if (error) return { ...base, tone: "unavailable", title: "Related findings unavailable", body: error };
  if (!packageId) return { ...base, tone: "unavailable", title: "Related findings unavailable", body: "No persisted Evidence Package identity is available for this record." };

  const limitations = (payload?.limitations ?? []).map(limitationLabel);
  switch (payload?.correlation_status) {
    case "related_packages_found":
      return {
        ...base,
        tone: "related",
        title: "Related findings observed",
        body: "These remain separate analytical findings. Each relationship is limited to persisted evidence dimensions.",
        items: (payload?.related_packages ?? []).map((relationship) => ({
          ...relationship,
          reason: describeRelationship(relationship),
          relationshipLabels: (relationship.supporting_relationships ?? []).map(relationshipLabel),
          limitationLabels: (relationship.limitations ?? []).map(limitationLabel),
        })),
        limitations,
      };
    case "no_supported_relationship":
      return { ...base, tone: "empty", title: "No supported related findings", body: "No other persisted package satisfies the v1 scope and relationship-anchor rules.", limitations };
    case "insufficient_evidence":
      return { ...base, tone: "unavailable", title: "Insufficient relationship evidence", body: "Package relationships require complete persisted scope evidence.", limitations };
    case "unavailable":
    default:
      return { ...base, tone: "unavailable", title: "Related findings unavailable", body: "No trusted relationship projection is available for this package.", limitations };
  }
}
