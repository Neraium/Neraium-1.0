import { describe, expect, it } from "vitest";
import { buildApiUrl } from "../../config";

describe("api path normalization", () => {
  it("keeps canonical api paths unchanged", () => {
    const url = buildApiUrl("/api/data/latest-upload?include_persisted=1");
    expect(url).toContain("/api/data/latest-upload?include_persisted=1");
  });

  it("normalizes legacy latest-upload shorthand", () => {
    const url = buildApiUrl("latest-upload?include_persisted=1");
    expect(url).toContain("/api/data/latest-upload?include_persisted=1");
  });

  it("normalizes slash-prefixed latest-upload shorthand", () => {
    const url = buildApiUrl("/latest-upload?include_persisted=1");
    expect(url).toContain("/api/data/latest-upload?include_persisted=1");
  });

  it("normalizes legacy systems shorthand", () => {
    const url = buildApiUrl("systems?include_persisted=1");
    expect(url).toContain("/api/facility/systems?include_persisted=1");
  });

  it("normalizes slash-prefixed systems shorthand", () => {
    const url = buildApiUrl("/systems?include_persisted=1");
    expect(url).toContain("/api/facility/systems?include_persisted=1");
  });

  it("normalizes slash-prefixed health shorthand", () => {
    const url = buildApiUrl("/health");
    expect(url).toContain("/api/health");
  });

  it("normalizes slash-prefixed mode shorthand", () => {
    const url = buildApiUrl("/mode");
    expect(url).toContain("/api/domain/mode");
  });

  it("normalizes slash-prefixed engine-identity shorthand", () => {
    const url = buildApiUrl("/engine-identity");
    expect(url).toContain("/api/intelligence/engine-identity");
  });
});
