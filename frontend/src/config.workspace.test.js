/* @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "./config";
import { setCurrentWorkspaceId } from "./services/datasetSessionCache";

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("workspace-scoped API requests", () => {
  it("sends the active workspace on latest-upload and upload-status requests", async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) }));
    vi.stubGlobal("fetch", fetchMock);
    setCurrentWorkspaceId("central-plant");

    await apiFetch("/api/data/latest-upload?include_persisted=true");
    await apiFetch("/api/data/upload-status/abc123");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    for (const [, options] of fetchMock.mock.calls) {
      expect(options.credentials).toBe("include");
      expect(options.headers["X-Neraium-Workspace-Id"]).toBe("central-plant");
    }
  });
});
