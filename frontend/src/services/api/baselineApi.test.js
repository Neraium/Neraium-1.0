/* @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from "vitest";
import { baselineQueryKey, clearBaselineResultCache, fetchBaselineResultById } from "./baselineApi";

function response(payload) {
  return { ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => payload, text: async () => JSON.stringify(payload) };
}

function result(portfolioId, filename) {
  return {
    job_id: `${portfolioId}-job`,
    dataset_id: `${portfolioId}-job`,
    established_baseline_id: "shared-baseline-id",
    portfolio_id: portfolioId,
    filename,
    candidate_model: { model_id: "shared-baseline-id", source: { job_id: `${portfolioId}-job`, filename } },
  };
}

afterEach(() => clearBaselineResultCache());

describe("baseline API cache scoping", () => {
  it("keys identical baseline IDs separately for different portfolios", async () => {
    const apiFetch = vi.fn(async (_path, options) => response(result(options.headers["X-Neraium-Workspace-Id"], `${options.headers["X-Neraium-Workspace-Id"]}.csv`)));

    const north = await fetchBaselineResultById({ apiFetch, portfolioId: "north", baselineId: "shared-baseline-id" });
    const south = await fetchBaselineResultById({ apiFetch, portfolioId: "south", baselineId: "shared-baseline-id" });
    const northCached = await fetchBaselineResultById({ apiFetch, portfolioId: "north", baselineId: "shared-baseline-id" });

    expect(baselineQueryKey("north", "shared-baseline-id")).not.toBe(baselineQueryKey("south", "shared-baseline-id"));
    expect(north.result.filename).toBe("north.csv");
    expect(south.result.filename).toBe("south.csv");
    expect(northCached.source).toBe("cache");
    expect(apiFetch).toHaveBeenCalledTimes(2);
  });
});
