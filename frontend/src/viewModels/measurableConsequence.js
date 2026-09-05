// Project recorded facts only; never integrate or infer a missing consequence in the UI.
const fields = [
  "status", "resource_type", "profile_key", "direction", "cumulative_amount", "cumulative_unit",
  "duration_seconds", "start_timestamp", "end_timestamp", "observation_count",
  "contributing_interval_count", "skipped_interval_count", "source_relationship_ids", "source_tag_ids",
  "finding_id", "evidence_id", "analysis_run_id", "support_level", "methodology", "methodology_version",
  "limitations", "statement",
];
export function consequenceSummary(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { status: "not_quantifiable", statement: "Consequence not quantifiable from available evidence." };
  }
  return Object.fromEntries(fields.filter((field) => Object.hasOwn(value, field)).map((field) => [field,
    Array.isArray(value[field]) ? [...value[field]] : value[field],
  ]));
}
