import { describe, expect, it } from "vitest";
import { deriveRoomContext, deriveTimeCoverage } from "../uploadState";

describe("uploadState normalization", () => {
  it("resolves room aliases from messy column names", () => {
    const result = {
      columns: ["Zone Name", "Growth-Stage", "Temp_C"],
      preview_rows: [
        { "Zone Name": "Flower-1", "Growth-Stage": "Late" },
      ],
      cultivation_mapping: { categories: { irrigation: [] } },
    };
    const context = deriveRoomContext(result);
    expect(context.primary).toBe("Flower-1");
    expect(context.cycle).toBe("Late");
  });

  it("derives timestamp coverage from preview rows when timestamp profile is missing", () => {
    const result = {
      columns: ["event_time", "Zone Name"],
      preview_rows: [
        { event_time: "2026-05-18T12:00:00Z" },
        { event_time: "2026-05-18T12:05:00Z" },
      ],
    };
    const coverage = deriveTimeCoverage(result);
    expect(coverage.hasCoverage).toBe(true);
    expect(coverage.summary).toContain("2026-05-18T12:00:00.000Z");
  });
});
