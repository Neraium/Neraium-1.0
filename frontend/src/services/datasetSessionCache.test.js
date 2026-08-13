/* @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CURRENT_WORKSPACE_STORAGE_KEY,
  DATASET_CACHE_SCOPE_STORAGE_KEY,
  activateDatasetCacheScope,
  clearDatasetSessionCache,
  datasetCacheScopeKey,
  getCurrentWorkspaceId,
  resolveAuthorizedWorkspaceSelection,
  setCurrentWorkspaceId,
} from "./datasetSessionCache";

const DATASET_LOCAL_KEYS = [
  "neraium.allow_persisted_latest",
  "neraium.last_upload_job_id",
  "neraium.completed_analysis_history",
];
const DATASET_SESSION_KEYS = ["neraium.session_intent"];

function seedDatasetCache() {
  DATASET_LOCAL_KEYS.forEach((key) => window.localStorage.setItem(key, `stale:${key}`));
  DATASET_SESSION_KEYS.forEach((key) => window.sessionStorage.setItem(key, `stale:${key}`));
}

function expectDatasetCacheCleared() {
  DATASET_LOCAL_KEYS.forEach((key) => expect(window.localStorage.getItem(key)).toBeNull());
  DATASET_SESSION_KEYS.forEach((key) => expect(window.sessionStorage.getItem(key)).toBeNull());
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("dataset session cache scoping", () => {
  it("clears stale upload metadata before adopting the authenticated user scope", () => {
    seedDatasetCache();

    const activation = activateDatasetCacheScope({ email: "Alice@Example.com" }, "central-plant");

    expect(activation).toEqual({ changed: true, scopeKey: "alice@example.com::central-plant", workspaceId: "central-plant" });
    expectDatasetCacheCleared();
    expect(window.localStorage.getItem(DATASET_CACHE_SCOPE_STORAGE_KEY)).toBe("alice@example.com::central-plant");
  });

  it("preserves legitimate cache entries while the user and workspace are unchanged", () => {
    activateDatasetCacheScope({ email: "alice@example.com" }, "central-plant");
    seedDatasetCache();

    const activation = activateDatasetCacheScope({ email: "alice@example.com" }, "central-plant");

    expect(activation.changed).toBe(false);
    DATASET_LOCAL_KEYS.forEach((key) => expect(window.localStorage.getItem(key)).toBe(`stale:${key}`));
    DATASET_SESSION_KEYS.forEach((key) => expect(window.sessionStorage.getItem(key)).toBe(`stale:${key}`));
  });

  it("clears cached dataset state when the authenticated user changes", () => {
    activateDatasetCacheScope({ email: "alice@example.com" }, "central-plant");
    seedDatasetCache();

    const activation = activateDatasetCacheScope({ email: "bob@example.com" }, "central-plant");

    expect(activation.changed).toBe(true);
    expectDatasetCacheCleared();
    expect(window.localStorage.getItem(DATASET_CACHE_SCOPE_STORAGE_KEY)).toBe("bob@example.com::central-plant");
  });

  it("clears cached dataset state and emits a refresh event when the workspace changes", () => {
    activateDatasetCacheScope({ email: "alice@example.com" }, "central-plant");
    seedDatasetCache();
    const listener = vi.fn();
    window.addEventListener("neraium:workspace-changed", listener);

    const workspaceId = setCurrentWorkspaceId("north-plant");

    expect(workspaceId).toBe("north-plant");
    expect(getCurrentWorkspaceId()).toBe("north-plant");
    expectDatasetCacheCleared();
    expect(window.localStorage.getItem(DATASET_CACHE_SCOPE_STORAGE_KEY)).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].detail).toEqual({ workspaceId: "north-plant" });
    window.removeEventListener("neraium:workspace-changed", listener);
  });

  it("clears cached dataset state and its owner on logout or revocation", () => {
    activateDatasetCacheScope({ email: "alice@example.com" }, "central-plant");
    seedDatasetCache();

    clearDatasetSessionCache();

    expectDatasetCacheCleared();
    expect(window.localStorage.getItem(DATASET_CACHE_SCOPE_STORAGE_KEY)).toBeNull();
    expect(window.localStorage.getItem(CURRENT_WORKSPACE_STORAGE_KEY)).toBeNull();
  });

  it("normalizes invalid or missing workspace identifiers to the default workspace", () => {
    window.localStorage.setItem(CURRENT_WORKSPACE_STORAGE_KEY, "../../another-tenant");

    expect(getCurrentWorkspaceId()).toBe("default");
    expect(datasetCacheScopeKey({ email: "alice@example.com" })).toBe("alice@example.com::default");
  });

  it("rejects a stale locally selected workspace against the authenticated session", () => {
    window.localStorage.setItem(CURRENT_WORKSPACE_STORAGE_KEY, "ws-former-facility");
    const session = {
      user: { email: "alice@example.com" },
      default_workspace_id: "default",
      workspaces: [
        { workspace_id: "default", display_name: "Personal workspace", kind: "personal", is_active: true },
        { workspace_id: "ws-central", display_name: "Central Plant", kind: "facility", is_active: true },
      ],
    };

    expect(resolveAuthorizedWorkspaceSelection(session)).toMatchObject({
      workspaceId: "default",
      currentWorkspace: { display_name: "Personal workspace" },
      stale: true,
    });
  });

  it("will not select an inactive workspace summary", () => {
    const session = {
      default_workspace_id: "ws-disabled",
      workspaces: [
        { workspace_id: "ws-disabled", display_name: "Disabled", kind: "facility", is_active: false },
        { workspace_id: "ws-active", display_name: "Active", kind: "facility", is_active: true },
      ],
    };

    expect(resolveAuthorizedWorkspaceSelection(session, "ws-disabled").workspaceId).toBe("ws-active");
  });

  it("keeps workspace startup usable when Safari denies storage access", () => {
    const denied = () => {
      throw new DOMException("Storage denied", "SecurityError");
    };
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(denied);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(denied);
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(denied);

    expect(getCurrentWorkspaceId()).toBe("default");
    expect(activateDatasetCacheScope({ email: "alice@example.com" }, "central-plant")).toEqual({
      changed: true,
      scopeKey: "alice@example.com::central-plant",
      workspaceId: "central-plant",
    });
    expect(() => clearDatasetSessionCache()).not.toThrow();
    expect(setCurrentWorkspaceId("north-plant")).toBe("north-plant");
  });
});
