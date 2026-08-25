import { describe, expect, it } from "vitest";
import { formatLocalTimestamp, resolveDisplayTimeZone, timestampTechnicalTitle } from "./dateTime";

describe("facility-aware timestamp presentation", () => {
  it("renders the stored instant in an explicit facility timezone", () => {
    expect(formatLocalTimestamp("2026-08-25T05:23:56.206210+00:00", "America/Los_Angeles")).toBe("Aug 24, 2026 · 10:23 PM PDT");
  });

  it("falls back safely when a facility timezone is invalid and preserves the source value", () => {
    expect(resolveDisplayTimeZone("not/a-timezone")).toBeTruthy();
    expect(timestampTechnicalTitle("2026-08-25T05:23:56.206210+00:00", "America/Los_Angeles")).toContain("2026-08-25T05:23:56.206210+00:00");
  });
});
