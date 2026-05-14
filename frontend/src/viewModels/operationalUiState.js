export function normalizeOperationalState(value) {
  const normalized = String(value ?? "").toLowerCase();

  if (!normalized || ["info", "idle", "pending", "checking", "processing", "empty", "muted", "neutral"].includes(normalized)) {
    return "neutral";
  }

  if (["stable", "nominal", "online", "ready", "normal", "active", "live"].includes(normalized)) {
    return "stable";
  }

  if (["review", "watch", "needs_review", "observing"].includes(normalized)) {
    return "watch";
  }

  if (["warning", "elevated", "degraded", "attention"].includes(normalized)) {
    return "warning";
  }

  if (["critical", "unstable", "offline", "not_ready", "separation", "action"].includes(normalized)) {
    return "critical";
  }

  return "neutral";
}

export function orbStateFromOperationalState(state) {
  if (state === "stable") {
    return "stable";
  }
  if (state === "watch") {
    return "watch";
  }
  if (state === "warning") {
    return "warning";
  }
  if (state === "critical") {
    return "critical";
  }
  return "neutral";
}
