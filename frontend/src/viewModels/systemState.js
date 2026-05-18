export function deriveIntelligenceMode({ hasRealSiiOutput, latestUploadSnapshot }) {
  if (hasRealSiiOutput) return "live";
  const status = String(latestUploadSnapshot?.status ?? latestUploadSnapshot?.processing_state ?? "").toLowerCase();
  if (["active", "baseline_active"].includes(status)) return "live";
  if (["queued", "pending", "uploading", "parsing", "baseline_modeling", "running_sii", "writing_state", "building_baseline"].includes(status)) {
    return "processing";
  }
  return "empty";
}

export function classifyDataFreshness({ heartbeatAt, now = Date.now(), online = true }) {
  if (!online) return { label: "Offline", tone: "offline" };
  if (!heartbeatAt) return { label: "No Data", tone: "empty" };
  const ts = new Date(heartbeatAt).getTime();
  if (!Number.isFinite(ts)) return { label: "No Data", tone: "empty" };
  const ageMs = Math.max(0, now - ts);
  if (ageMs <= 2 * 60 * 1000) return { label: "Live", tone: "live" };
  if (ageMs <= 10 * 60 * 1000) return { label: "Aging", tone: "aging" };
  return { label: "Stale", tone: "stale" };
}
