import { describe, expect, it } from "vitest";
import { classifyDataFreshness, deriveIntelligenceMode } from "../systemState";

describe("systemState", () => {
  it("derives processing mode from upload status", () => {
    expect(deriveIntelligenceMode({
      hasRealSiiOutput: false,
      latestUploadSnapshot: { status: "running_sii" },
    })).toBe("processing");
  });

  it("keeps active status in processing mode without full SII proof", () => {
    expect(deriveIntelligenceMode({
      hasRealSiiOutput: false,
      latestUploadSnapshot: { status: "active" },
    })).toBe("processing");
  });

  it("classifies stale freshness when heartbeat is old", () => {
    const now = new Date("2026-05-18T12:00:00.000Z").getTime();
    const heartbeat = new Date("2026-05-18T11:45:00.000Z").toISOString();
    expect(classifyDataFreshness({ heartbeatAt: heartbeat, now, online: true }).label).toBe("Stale");
  });
});
