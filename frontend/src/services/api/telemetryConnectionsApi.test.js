import { describe, expect, it, vi } from "vitest";
import { getTelemetryAnalysisResultLineage } from "./telemetryConnectionsApi";

function response(payload) {
  return { ok: true, status: 200, json: async () => payload };
}

describe("telemetry connections API", () => {
  it("requests the complete bounded canonical lineage in one product read", async () => {
    const apiFetch = vi.fn().mockResolvedValue(response({ records: [] }));

    await getTelemetryAnalysisResultLineage({
      apiFetch,
      connectionId: "11111111-1111-4111-8111-111111111111",
      runId: "22222222-2222-4222-8222-222222222222",
      systemId: "plant/chw-loop",
      resultId: "33333333-3333-4333-8333-333333333333",
      limit: 5_000,
    });

    expect(apiFetch.mock.calls[0][0]).toContain(
      "/systems/plant%2Fchw-loop/analysis-results/33333333-3333-4333-8333-333333333333/lineage?limit=5000",
    );
  });
});
