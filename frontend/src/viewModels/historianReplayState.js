function mapReplayStateToTone(state) {
  const normalized = String(state ?? "").toLowerCase();
  if (normalized.includes("alert") || normalized.includes("instab")) return "unstable";
  if (normalized.includes("drift")) return "elevated";
  if (normalized.includes("watch")) return "review";
  if (normalized.includes("recover")) return "review";
  return "nominal";
}

export function buildReplayLiveOps(baseLiveOps, frame) {
  if (!frame) return baseLiveOps;
  const tone = mapReplayStateToTone(frame.structural_state ?? frame.topology_state?.stability_state);
  const contributors = Array.isArray(frame.primary_contributors) ? frame.primary_contributors : [];
  const contributorText = contributors.length ? contributors.join(", ") : "No dominant contributor";
  const affectedArea = frame.affected_area ?? frame.affected_subsystem ?? baseLiveOps.primaryWindow?.label ?? "Facility scope";

  return {
    ...baseLiveOps,
    facilityTone: tone,
    facilityStateLabel: frame.structural_state ?? frame.topology_state?.stability_state ?? baseLiveOps.facilityStateLabel,
    heroTag: "Replay Mode",
    heroHeadline: frame.structural_state ?? "Historian replay",
    heroSubline: frame.operator_summary ?? frame.operator_interpretation ?? baseLiveOps.heroSubline,
    connectionSummary: `Replay ${frame.frame_index + 1}/${frame.total_frames ?? "?"} | ${frame.timestamp_end ?? frame.timestamp ?? ""}`.trim(),
    connectionStatusLine: "Replay Mode active. Views are driven by historian playback.",
    connectionActionHint: frame.operator_focus ?? "Follow structural progression frame by frame.",
    primaryWindow: {
      ...(baseLiveOps.primaryWindow ?? {}),
      label: affectedArea,
      status: frame.structural_state ?? baseLiveOps.primaryWindow?.status ?? "Replay",
      window: frame.timestamp_end ?? frame.timestamp ?? baseLiveOps.primaryWindow?.window ?? "Replay",
      tone,
      summary: frame.operator_summary ?? baseLiveOps.primaryWindow?.summary,
      recommendation: frame.operator_focus ?? baseLiveOps.primaryWindow?.recommendation,
    },
    findings: [
      { title: "Structural read", detail: frame.structural_state ?? "Replay", tone },
      { title: "Primary contributors", detail: contributorText, tone: "review" },
      { title: "Current window", detail: `${frame.timestamp_start ?? "-"} -> ${frame.timestamp_end ?? frame.timestamp ?? "-"}`, tone: "info" },
    ],
    relationshipRows: (frame.relationship_changes ?? []).map((path) => ({
      pair_key: String(path),
      columns: String(path).split("_"),
      change: frame.relationship_drift ?? frame.baseline_separation ?? frame.baseline_distance ?? 0,
      pair_weight: frame.relationship_drift ?? 0,
      tone,
      detail: `Relationship change observed: ${path}`,
    })),
    driftRows: [{
      column: "baseline_separation",
      direction: "up",
      drift_flag: tone,
      baseline_average: 0,
      recent_average: frame.baseline_separation ?? frame.baseline_distance ?? 0,
      absolute_change: frame.drift_velocity ?? 0,
      detail: frame.operator_interpretation ?? "Replay frame diagnostics",
    }],
    evidenceLines: [
      `replay.frame_index=${frame.frame_index}`,
      `replay.total_frames=${frame.total_frames ?? ""}`,
      `replay.structural_state=${frame.structural_state ?? ""}`,
      `replay.evidence_confidence=${frame.evidence_confidence ?? ""}`,
    ],
  };
}
