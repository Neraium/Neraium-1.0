/* @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from "vitest";
import { clearFacilitySystemsCache, fetchFacilitySystems } from "./systemApi";

function response(systemId) {
  return { ok: true, status: 200, json: async () => ({ systems: [{ id: systemId }] }) };
}

afterEach(() => clearFacilitySystemsCache());

describe("facility systems cache ownership", () => {
  it("separates identical portfolio queries by authenticated scope", async () => {
    const apiFetch = vi.fn()
      .mockResolvedValueOnce(response("user-a-system"))
      .mockResolvedValueOnce(response("user-b-system"));

    const userA = await fetchFacilitySystems({ apiFetch, scopeKey: "user-a::default", portfolioId: "default" });
    const userB = await fetchFacilitySystems({ apiFetch, scopeKey: "user-b::default", portfolioId: "default" });

    expect(userA.systems[0].id).toBe("user-a-system");
    expect(userB.systems[0].id).toBe("user-b-system");
    expect(apiFetch).toHaveBeenCalledTimes(2);
    expect(apiFetch.mock.calls[0][1].headers).toEqual({ "X-Neraium-Workspace-Id": "default" });
  });

  it("separates queries by portfolio and domain mode", async () => {
    const apiFetch = vi.fn()
      .mockResolvedValueOnce(response("north-system"))
      .mockResolvedValueOnce(response("south-system"));

    await fetchFacilitySystems({ apiFetch, scopeKey: "user-a", portfolioId: "north", domainMode: "aquatic" });
    await fetchFacilitySystems({ apiFetch, scopeKey: "user-a", portfolioId: "south", domainMode: "aquatic" });

    expect(apiFetch).toHaveBeenCalledTimes(2);
    expect(apiFetch.mock.calls[0][0]).toContain("domain_mode=aquatic");
    expect(apiFetch.mock.calls[0][1].headers["X-Neraium-Workspace-Id"]).toBe("north");
    expect(apiFetch.mock.calls[1][1].headers["X-Neraium-Workspace-Id"]).toBe("south");
  });

  it("does not request persisted facility results unless explicitly enabled", async () => {
    const apiFetch = vi.fn().mockResolvedValue(response("current-system"));

    await fetchFacilitySystems({ apiFetch, scopeKey: "user-a", portfolioId: "north" });
    await fetchFacilitySystems({ apiFetch, scopeKey: "user-a", portfolioId: "north", includePersisted: true });

    expect(apiFetch.mock.calls[0][0]).toContain("include_persisted=0");
    expect(apiFetch.mock.calls[1][0]).toContain("include_persisted=1");
  });
});
