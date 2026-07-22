export const CURRENT_WORKSPACE_STORAGE_KEY = "neraium.current_workspace_id";
export const DATASET_CACHE_SCOPE_STORAGE_KEY = "neraium.dataset_cache_scope";
export const DEFAULT_DATA_WORKSPACE_ID = "default";

const LOCAL_DATASET_CACHE_KEYS = [
  "neraium.allow_persisted_latest",
  "neraium.last_upload_job_id",
  "neraium.completed_analysis_history",
];
const SESSION_DATASET_CACHE_KEYS = [
  "neraium.session_intent",
];
const WORKSPACE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

function normalizeWorkspaceId(value) {
  const normalized = String(value ?? "").trim();
  return WORKSPACE_PATTERN.test(normalized) ? normalized : DEFAULT_DATA_WORKSPACE_ID;
}

function normalizeUserId(user) {
  return String(user?.email ?? user?.id ?? user ?? "").trim().toLowerCase();
}

export function getCurrentWorkspaceId() {
  if (typeof window === "undefined") return DEFAULT_DATA_WORKSPACE_ID;
  return normalizeWorkspaceId(window.localStorage.getItem(CURRENT_WORKSPACE_STORAGE_KEY));
}

export function datasetCacheScopeKey(user, workspaceId = getCurrentWorkspaceId()) {
  const userId = normalizeUserId(user);
  if (!userId) return "signed-out";
  return `${userId}::${normalizeWorkspaceId(workspaceId)}`;
}

export function clearDatasetSessionCache({ clearScopeOwner = true, clearWorkspace = true } = {}) {
  if (typeof window === "undefined") return;
  LOCAL_DATASET_CACHE_KEYS.forEach((key) => window.localStorage.removeItem(key));
  SESSION_DATASET_CACHE_KEYS.forEach((key) => window.sessionStorage.removeItem(key));
  if (clearScopeOwner) window.localStorage.removeItem(DATASET_CACHE_SCOPE_STORAGE_KEY);
  if (clearWorkspace) window.localStorage.removeItem(CURRENT_WORKSPACE_STORAGE_KEY);
}

export function activateDatasetCacheScope(user, workspaceId = null) {
  const hasExplicitWorkspace = workspaceId !== null && workspaceId !== undefined;
  let resolvedWorkspaceId = normalizeWorkspaceId(hasExplicitWorkspace ? workspaceId : getCurrentWorkspaceId());
  if (typeof window === "undefined") {
    const scopeKey = datasetCacheScopeKey(user, resolvedWorkspaceId);
    return { changed: false, scopeKey, workspaceId: resolvedWorkspaceId };
  }
  const previousScopeKey = window.localStorage.getItem(DATASET_CACHE_SCOPE_STORAGE_KEY);
  const previousUserId = String(previousScopeKey ?? "").split("::", 1)[0];
  const nextUserId = normalizeUserId(user);
  if (!hasExplicitWorkspace && previousUserId && previousUserId !== nextUserId) {
    window.localStorage.removeItem(CURRENT_WORKSPACE_STORAGE_KEY);
    resolvedWorkspaceId = DEFAULT_DATA_WORKSPACE_ID;
  }
  const scopeKey = datasetCacheScopeKey(user, resolvedWorkspaceId);
  const changed = previousScopeKey !== scopeKey;
  if (changed) clearDatasetSessionCache({ clearScopeOwner: false, clearWorkspace: false });
  window.localStorage.setItem(DATASET_CACHE_SCOPE_STORAGE_KEY, scopeKey);
  return { changed, scopeKey, workspaceId: resolvedWorkspaceId };
}

export function setCurrentWorkspaceId(workspaceId) {
  const normalized = normalizeWorkspaceId(workspaceId);
  if (typeof window === "undefined") return normalized;
  const previous = getCurrentWorkspaceId();
  window.localStorage.setItem(CURRENT_WORKSPACE_STORAGE_KEY, normalized);
  if (previous !== normalized) {
    clearDatasetSessionCache({ clearWorkspace: false });
    window.dispatchEvent(new CustomEvent("neraium:workspace-changed", { detail: { workspaceId: normalized } }));
  }
  return normalized;
}
