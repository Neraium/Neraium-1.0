import { describe, expect, it, vi } from "vitest";
import { fetchRelatedEvidencePackages } from "./evidenceCorrelationApi";

describe("evidence correlation API", () => {
  it("encodes package identity and performs a pure no-cache read", async () => {
    const payload = { correlation_status: "no_supported_relationship" };
    const apiFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => payload });
    const controller = new AbortController();

    await expect(fetchRelatedEvidencePackages({ apiFetch, packageId: "package#1", signal: controller.signal })).resolves.toEqual(payload);
    expect(apiFetch).toHaveBeenCalledWith(
      "/api/data/evidence-packages/package%231/related-packages",
      { cache: "no-store", signal: controller.signal },
    );
  });

  it("surfaces the API detail without inventing a relationship state", async () => {
    const apiFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: "Evidence Package was not found." }),
    });

    await expect(fetchRelatedEvidencePackages({ apiFetch, packageId: "missing" })).rejects.toMatchObject({
      message: "Evidence Package was not found.",
      status: 404,
    });
  });
});
