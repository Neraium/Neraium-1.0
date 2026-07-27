/* @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

function response(status, contentType = "application/json") {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name) => name.toLowerCase() === "content-type" ? contentType : null },
  };
}

async function loadConfiguredApi() {
  vi.resetModules();
  vi.stubEnv("VITE_API_BASE_URL", "https://configured-api.example.test");
  return import("./config");
}

describe("configured API fallback", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("uses same-origin after a configured host network failure", async () => {
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new TypeError("DNS unavailable"))
      .mockResolvedValueOnce(response(200));
    vi.stubGlobal("fetch", fetchMock);
    const { apiFetch } = await loadConfiguredApi();

    await expect(apiFetch("/api/auth/me", { expectedResponseType: "json", timeoutMs: 1000 }))
      .resolves.toMatchObject({ status: 200 });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe("https://configured-api.example.test/api/auth/me");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/auth/me");
  });

  it("uses same-origin when the configured host returns app HTML", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(200, "text/html"))
      .mockResolvedValueOnce(response(200));
    vi.stubGlobal("fetch", fetchMock);
    const { apiFetch } = await loadConfiguredApi();

    const result = await apiFetch("/api/auth/me", { expectedResponseType: "json", timeoutMs: 1000 });

    expect(result.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][0]).toBe("/api/auth/me");
  });

  it("reports a network error after both API candidates fail", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("offline"));
    vi.stubGlobal("fetch", fetchMock);
    const { apiFetch } = await loadConfiguredApi();

    await expect(apiFetch("/api/auth/me", { expectedResponseType: "json", timeoutMs: 1000 }))
      .rejects.toMatchObject({ name: "ApiNetworkError" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not retry an authoritative 401 response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(401));
    vi.stubGlobal("fetch", fetchMock);
    const { apiFetch } = await loadConfiguredApi();

    await expect(apiFetch("/api/auth/me", { expectedResponseType: "json", timeoutMs: 1000 }))
      .resolves.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not replay mutating requests against a fallback candidate", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("connection lost"));
    vi.stubGlobal("fetch", fetchMock);
    const { apiFetch } = await loadConfiguredApi();

    await expect(apiFetch("/api/data/upload-session", {
      method: "POST",
      body: "{}",
      timeoutMs: 1000,
    })).rejects.toMatchObject({ name: "ApiNetworkError" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("propagates caller cancellation without trying another candidate", async () => {
    const fetchMock = vi.fn((_url, options) => new Promise((resolve, reject) => {
      options.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
      void resolve;
    }));
    vi.stubGlobal("fetch", fetchMock);
    const { apiFetch } = await loadConfiguredApi();
    const controller = new AbortController();

    const request = apiFetch("/api/auth/me", { signal: controller.signal, timeoutMs: 1000 });
    controller.abort();

    await expect(request).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
