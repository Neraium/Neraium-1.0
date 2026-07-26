/* @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { setCurrentWorkspaceId } from "../datasetSessionCache";
import { clearFacilitySystemsCache, fetchFacilitySystems } from "./systemApi";

function response(payload) {
  return { ok: true, status: 200, json: async () => payload };
}

describe("facility systems workspace cache", () => {
  beforeEach(() => {
    window.localStorage.clear();
    clearFacilitySystemsCache();
  });

  it("does not reuse systems from another workspace", async () => {
    const apiFetch = vi.fn()
      .mockResolvedValueOnce(response({ systems: [{ id: "central-system" }] }))
      .mockResolvedValueOnce(response({ systems: [{ id: "north-system" }] }));

    setCurrentWorkspaceId("central-plant");
    const central = await fetchFacilitySystems({ apiFetch, accessCode: "" });
    setCurrentWorkspaceId("north-plant");
    const north = await fetchFacilitySystems({ apiFetch, accessCode: "" });

    expect(central.systems[0].id).toBe("central-system");
    expect(north.systems[0].id).toBe("north-system");
    expect(apiFetch).toHaveBeenCalledTimes(2);
  });

  it("cannot repopulate a cleared cache from an older in-flight request", async () => {
    let resolveOldRequest;
    const oldRequest = new Promise((resolve) => { resolveOldRequest = resolve; });
    const apiFetch = vi.fn()
      .mockReturnValueOnce(oldRequest)
      .mockResolvedValueOnce(response({ systems: [{ id: "current-system" }] }));

    setCurrentWorkspaceId("central-plant");
    const stalePromise = fetchFacilitySystems({ apiFetch, accessCode: "" });
    clearFacilitySystemsCache();
    setCurrentWorkspaceId("north-plant");
    const current = await fetchFacilitySystems({ apiFetch, accessCode: "" });
    resolveOldRequest(response({ systems: [{ id: "stale-system" }] }));
    await stalePromise;
    const cachedCurrent = await fetchFacilitySystems({ apiFetch, accessCode: "" });

    expect(current.systems[0].id).toBe("current-system");
    expect(cachedCurrent.systems[0].id).toBe("current-system");
    expect(apiFetch).toHaveBeenCalledTimes(2);
  });
});
