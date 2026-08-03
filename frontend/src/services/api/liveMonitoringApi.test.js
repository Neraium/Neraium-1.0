/* @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";

import {
  fetchLiveAnalysisConfigurations,
  fetchLiveMonitoringSnapshot,
} from "./liveMonitoringApi";

const PAYLOADS = {
  "/api/live-analysis/configurations": { configurations: [{ system_id: "plant-a" }] },
  "/api/telemetry/ingestion-health": { health: [{ system_id: "plant-a", source: "historian" }] },
  "/api/live-analysis/health": { health: [{ system_id: "plant-a", current_status: "healthy" }] },
  "/api/live-analysis/runs?limit=100": { runs: [{ run_id: "run-1" }] },
  "/api/live-analysis/findings?limit=100": { findings: [{ finding_id: "finding-1" }] },
};

function response(payload, { ok = true, status = 200 } = {}) {
  return { ok, status, json: vi.fn(async () => payload) };
}

describe("Live Monitoring API", () => {
  it("loads every Phase 1 and Phase 2 read endpoint with existing request conventions", async () => {
    const apiFetch = vi.fn(async (path) => response(PAYLOADS[path]));

    const snapshot = await fetchLiveMonitoringSnapshot({ apiFetch, accessCode: "test-token" });

    expect(snapshot.status).toBe("complete");
    expect(snapshot.configurations).toEqual([{ system_id: "plant-a" }]);
    expect(snapshot.ingestionHealth).toHaveLength(1);
    expect(snapshot.analysisHealth).toHaveLength(1);
    expect(snapshot.runs).toHaveLength(1);
    expect(snapshot.findings).toHaveLength(1);
    expect(apiFetch.mock.calls.map(([path]) => path)).toEqual(Object.keys(PAYLOADS));
    for (const [, options] of apiFetch.mock.calls) {
      expect(options).toMatchObject({
        accessCode: "test-token",
        cache: "no-store",
        expectedResponseType: "json",
      });
    }
  });

  it("coalesces overlapping workspace refreshes", async () => {
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    const apiFetch = vi.fn(async (path) => {
      await gate;
      return response(PAYLOADS[path]);
    });

    const first = fetchLiveMonitoringSnapshot({ apiFetch });
    const second = fetchLiveMonitoringSnapshot({ apiFetch });
    expect(second).toBe(first);
    release();
    await Promise.all([first, second]);

    expect(apiFetch).toHaveBeenCalledTimes(5);
  });

  it("keeps successful collections when one endpoint fails", async () => {
    const apiFetch = vi.fn(async (path) => (
      path === "/api/live-analysis/health"
        ? response({}, { ok: false, status: 503 })
        : response(PAYLOADS[path])
    ));

    const snapshot = await fetchLiveMonitoringSnapshot({ apiFetch });

    expect(snapshot.status).toBe("partial");
    expect(snapshot.analysisHealth).toEqual([]);
    expect(snapshot.errors.analysisHealth).toMatchObject({ kind: "http", status: 503 });
    expect(snapshot.configurations).toHaveLength(1);
    expect(snapshot.findings).toHaveLength(1);
  });

  it("classifies a fully unauthorized snapshot without exposing response bodies", async () => {
    const apiFetch = vi.fn(async () => response({ detail: "internal authorization detail" }, { ok: false, status: 401 }));

    const snapshot = await fetchLiveMonitoringSnapshot({ apiFetch });

    expect(snapshot.status).toBe("unauthorized");
    expect(Object.values(snapshot.errors)).toHaveLength(5);
    expect(JSON.stringify(snapshot.errors)).not.toContain("internal authorization detail");
  });

  it("rejects malformed collection payloads", async () => {
    const apiFetch = vi.fn(async () => response({ configurations: null }));

    await expect(fetchLiveAnalysisConfigurations({ apiFetch })).rejects.toMatchObject({
      name: "LiveMonitoringRequestError",
      kind: "malformed-response",
      path: "/api/live-analysis/configurations",
    });
  });
});
