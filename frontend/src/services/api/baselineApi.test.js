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
    system_id: `${portfolioId}-system`,
    filename,
    candidate_model: {
      model_id: "shared-baseline-id",
      baseline_id: "shared-baseline-id",
      source: {
        job_id: `${portfolioId}-job`,
        filename,
        portfolio_id: portfolioId,
        system_id: `${portfolioId}-system`,
      },
    },
    analysis_state: { status: "empty", count: 0, analyses: [] },
  };
}

afterEach(() => clearBaselineResultCache());

describe("baseline API cache scoping", () => {
  it("keys identical baseline IDs separately for different portfolios", async () => {
    const apiFetch = vi.fn(async (_path, options) => response(result(options.headers["X-Neraium-Workspace-Id"], `${options.headers["X-Neraium-Workspace-Id"]}.csv`)));

    const north = await fetchBaselineResultById({ apiFetch, scopeKey: "user-a", portfolioId: "north", baselineId: "shared-baseline-id" });
    const south = await fetchBaselineResultById({ apiFetch, scopeKey: "user-a", portfolioId: "south", baselineId: "shared-baseline-id" });
    const northCached = await fetchBaselineResultById({ apiFetch, scopeKey: "user-a", portfolioId: "north", baselineId: "shared-baseline-id" });

    expect(baselineQueryKey("user-a", "north", "shared-baseline-id")).not.toBe(baselineQueryKey("user-a", "south", "shared-baseline-id"));
    expect(north.result.filename).toBe("north.csv");
    expect(south.result.filename).toBe("south.csv");
    expect(northCached.source).toBe("cache");
    expect(apiFetch).toHaveBeenCalledTimes(2);
    expect(apiFetch.mock.calls[0][0]).toBe("/api/data/portfolios/north/baselines/shared-baseline-id");
    expect(apiFetch.mock.calls[0][1]).toMatchObject({
      timeoutMs: 15_000,
      headers: { "X-Neraium-Workspace-Id": "north" },
    });
    expect(apiFetch.mock.calls[0][1].headers["X-Request-Id"]).toMatch(/^baseline-detail-/);
  });

  it("never reuses an identical portfolio/baseline cache entry across user scopes", async () => {
    const apiFetch = vi.fn(async (_path, options) => response(result(options.headers["X-Neraium-Workspace-Id"], `${options.headers["X-Request-Id"]}.csv`)));

    await fetchBaselineResultById({ apiFetch, scopeKey: "user-a", portfolioId: "north", baselineId: "shared-baseline-id" });
    await fetchBaselineResultById({ apiFetch, scopeKey: "user-b", portfolioId: "north", baselineId: "shared-baseline-id" });

    expect(apiFetch).toHaveBeenCalledTimes(2);
    expect(baselineQueryKey("user-a", "north", "shared-baseline-id")).not.toBe(baselineQueryKey("user-b", "north", "shared-baseline-id"));
  });

  it("returns safe timeout diagnostics with a retryable request identifier", async () => {
    const apiFetch = vi.fn(async () => {
      const error = new Error("internal transport text");
      error.name = "ApiTimeoutError";
      throw error;
    });

    await expect(fetchBaselineResultById({
      apiFetch,
      scopeKey: "user-a",
      portfolioId: "north",
      baselineId: "shared-baseline-id",
    })).rejects.toMatchObject({
      name: "BaselineRequestError",
      errorType: "timeout",
      status: 408,
      retryable: true,
      path: "/api/data/portfolios/north/baselines/shared-baseline-id",
    });
  });

  it("rejects a successful response owned by another system or portfolio", async () => {
    const apiFetch = vi.fn(async () => response(result("south", "wrong.csv")));

    await expect(fetchBaselineResultById({
      apiFetch,
      scopeKey: "user-a",
      portfolioId: "north",
      baselineId: "shared-baseline-id",
    })).rejects.toMatchObject({
      name: "BaselineRequestError",
      errorType: "baseline_request_failed",
    });
  });
});
