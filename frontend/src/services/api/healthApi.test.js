import { describe, expect, it, vi } from "vitest";

import { fetchApiHealth } from "./healthApi";

function deferred() {
  let resolve;
  const promise = new Promise((next) => { resolve = next; });
  return { promise, resolve };
}

describe("fetchApiHealth", () => {
  it("starts readiness and health requests together to avoid a startup waterfall", async () => {
    const health = deferred();
    const ready = deferred();
    const apiFetch = vi.fn((path) => (path === "/api/health" ? health.promise : ready.promise));

    const request = fetchApiHealth({ apiFetch, accessCode: "" });

    expect(apiFetch.mock.calls.map(([path]) => path)).toEqual(["/api/ready", "/api/health"]);
    health.resolve({ ok: true, json: async () => ({ status: "ok" }) });
    ready.resolve({ ok: true, json: async () => ({ status: "ready", queue: { pending: 0 } }) });

    await expect(request).resolves.toEqual({
      status: "ok",
      ready: { status: "ready", queue: { pending: 0 } },
    });
  });

  it("keeps readiness diagnostics optional", async () => {
    const apiFetch = vi.fn(async (path) => {
      if (path === "/api/ready") throw new Error("not ready");
      return { ok: true, json: async () => ({ status: "ok" }) };
    });

    await expect(fetchApiHealth({ apiFetch, accessCode: "" })).resolves.toEqual({
      status: "ok",
      ready: null,
    });
  });
});
