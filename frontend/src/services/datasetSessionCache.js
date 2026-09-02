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
const BASELINE_SELECTION_STORAGE_PREFIX = "neraium.baseline_selection.";
const WORKSPACE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

function normalizeWorkspaceId(value) {
  const normalized = String(value ?? "").trim();
  return WORKSPACE_PATTERN.test(normalized) ? normalized : DEFAULT_DATA_WORKSPACE_ID;
}

function activeWorkspaceSummaries(session) {
  const summaries = Array.isArray(session?.workspaces) ? session.workspaces : [];
  const normalized = summaries
    .filter((workspace) => workspace && workspace.is_active !== false && WORKSPACE_PATTERN.test(String(workspace.workspace_id ?? "").trim()))
    .map((workspace) => ({
      ...workspace,
      workspace_id: String(workspace.workspace_id).trim(),
      display_name: String(workspace.display_name || "Facility workspace").trim(),
    }))
    .filter((workspace, index, all) => all.findIndex((candidate) => candidate.workspace_id === workspace.workspace_id) === index);
  if (normalized.length) return normalized;
  return [{ workspace_id: DEFAULT_DATA_WORKSPACE_ID, display_name: "Personal workspace", kind: "personal", is_active: true }];
}

function normalizeUserId(user) {
  return String(user?.email ?? user?.id ?? user ?? "").trim().toLowerCase();
}

function resolveBrowserStorage(storageName) {
  try {
    return window[storageName];
  } catch {
    return null;
  }
}

function readStorageItem(storage, key) {
  try {
    return storage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

function writeStorageItem(storage, key, value) {
  try {
    storage?.setItem(key, value);
  } catch {
    // Storage is a cache only. Safari privacy settings may deny access.
  }
}

function removeStorageItem(storage, key) {
  try {
    storage?.removeItem(key);
  } catch {
    // Keep session verification independent from optional browser storage.
  }
}

export function getCurrentWorkspaceId() {
  if (typeof window === "undefined") return DEFAULT_DATA_WORKSPACE_ID;
  return normalizeWorkspaceId(readStorageItem(resolveBrowserStorage("localStorage"), CURRENT_WORKSPACE_STORAGE_KEY));
}

export function datasetCacheScopeKey(user, workspaceId = getCurrentWorkspaceId()) {
  const userId = normalizeUserId(user);
  if (!userId) return "signed-out";
  return `${userId}::${normalizeWorkspaceId(workspaceId)}`;
}

export function resolveAuthorizedWorkspaceSelection(session, requestedWorkspaceId = getCurrentWorkspaceId()) {
  const workspaces = activeWorkspaceSummaries(session);
  const allowedIds = new Set(workspaces.map((workspace) => workspace.workspace_id));
  const requested = normalizeWorkspaceId(requestedWorkspaceId);
  const configuredDefault = normalizeWorkspaceId(session?.default_workspace_id);
  const workspaceId = allowedIds.has(requested)
    ? requested
    : allowedIds.has(configuredDefault)
      ? configuredDefault
      : workspaces[0].workspace_id;
  return {
    workspaceId,
    currentWorkspace: workspaces.find((workspace) => workspace.workspace_id === workspaceId) ?? workspaces[0],
    workspaces,
    stale: workspaceId !== requested,
  };
}

export function activateAuthorizedWorkspaceSession(session) {
  const selection = resolveAuthorizedWorkspaceSelection(session);
  setCurrentWorkspaceId(selection.workspaceId);
  const activation = activateDatasetCacheScope(session?.user, selection.workspaceId);
  return { ...selection, scopeKey: activation.scopeKey, changed: activation.changed };
}

export function clearDatasetSessionCache({ clearScopeOwner = true, clearWorkspace = true } = {}) {
  if (typeof window === "undefined") return;
  const localStorage = resolveBrowserStorage("localStorage");
  const sessionStorage = resolveBrowserStorage("sessionStorage");
  LOCAL_DATASET_CACHE_KEYS.forEach((key) => removeStorageItem(localStorage, key));
  try {
    for (let index = localStorage?.length - 1; index >= 0; index -= 1) {
      const key = localStorage.key(index);
      if (key?.startsWith(BASELINE_SELECTION_STORAGE_PREFIX)) removeStorageItem(localStorage, key);
    }
  } catch {
    // Prefix cleanup is best effort when browser storage is unavailable.
  }
  SESSION_DATASET_CACHE_KEYS.forEach((key) => removeStorageItem(sessionStorage, key));
  if (clearScopeOwner) removeStorageItem(localStorage, DATASET_CACHE_SCOPE_STORAGE_KEY);
  if (clearWorkspace) removeStorageItem(localStorage, CURRENT_WORKSPACE_STORAGE_KEY);
}

export function activateDatasetCacheScope(user, workspaceId = null) {
  const hasExplicitWorkspace = workspaceId !== null && workspaceId !== undefined;
  let resolvedWorkspaceId = normalizeWorkspaceId(hasExplicitWorkspace ? workspaceId : getCurrentWorkspaceId());
  if (typeof window === "undefined") {
    const scopeKey = datasetCacheScopeKey(user, resolvedWorkspaceId);
    return { changed: false, scopeKey, workspaceId: resolvedWorkspaceId };
  }
  const localStorage = resolveBrowserStorage("localStorage");
  const previousScopeKey = readStorageItem(localStorage, DATASET_CACHE_SCOPE_STORAGE_KEY);
  const previousUserId = String(previousScopeKey ?? "").split("::", 1)[0];
  const nextUserId = normalizeUserId(user);
  if (!hasExplicitWorkspace && previousUserId && previousUserId !== nextUserId) {
    removeStorageItem(localStorage, CURRENT_WORKSPACE_STORAGE_KEY);
    resolvedWorkspaceId = DEFAULT_DATA_WORKSPACE_ID;
  }
  const scopeKey = datasetCacheScopeKey(user, resolvedWorkspaceId);
  const changed = previousScopeKey !== scopeKey;
  if (changed) clearDatasetSessionCache({ clearScopeOwner: false, clearWorkspace: false });
  writeStorageItem(localStorage, DATASET_CACHE_SCOPE_STORAGE_KEY, scopeKey);
  return { changed, scopeKey, workspaceId: resolvedWorkspaceId };
}

export function setCurrentWorkspaceId(workspaceId) {
  const normalized = normalizeWorkspaceId(workspaceId);
  if (typeof window === "undefined") return normalized;
  const previous = getCurrentWorkspaceId();
  writeStorageItem(resolveBrowserStorage("localStorage"), CURRENT_WORKSPACE_STORAGE_KEY, normalized);
  if (previous !== normalized) {
    clearDatasetSessionCache({ clearWorkspace: false });
    window.dispatchEvent(new CustomEvent("neraium:workspace-changed", { detail: { workspaceId: normalized } }));
  }
  return normalized;
}
