/* @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  CURRENT_WORKSPACE_STORAGE_KEY,
  DATASET_CACHE_SCOPE_STORAGE_KEY,
  activateDatasetCacheScope,
  clearDatasetSessionCache,
  datasetCacheScopeKey,
  getCurrentWorkspaceId,
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
});
