// Historical attribution fields are parseable input, never current analytical output.
const retired = new Set([
  "cause", "causes", "likelycause", "likelycauses", "probablecause", "suspectedcause", "rootcause",
  "diagnosis", "diagnosticconclusion", "automatedcorrectiveaction", "causeestablished", "causeconfirmed",
  "causeattribution", "attributionstatus", "potentialoperationalcauses", "possibleoperationalcauses", "possibleoperationalcausessummary",
  "possibleexplanations", "alternativeexplanations", "whyneraiumthinksithappened", "whyneraiumthinks",
  "likelydriver", "primarydriver", "primarydrivers", "driverattribution", "counterfactualdriverranking",
]);
const immutable = new Set(["measurable_consequence", "provenance", "source_tag_ids", "source_relationship_ids", "normalized_telemetry", "telemetry_signal_catalog", "telemetry_signals", "source_rows", "observations", "rows"]);
export function productEvidence(value) {
  if (Array.isArray(value)) return value.map(productEvidence);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value)
    .filter(([key]) => !retired.has(key.replaceAll("_", "").toLowerCase()))
    .map(([key, item]) => [key, immutable.has(key) ? item : productEvidence(item)]));
}
