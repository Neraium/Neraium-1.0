/* @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../../config";
import { fetchCurrentUser, loginUser, logoutUser, SESSION_INITIALIZATION_ERROR_KIND } from "./authApi";

vi.mock("../../config", () => ({ apiFetch: vi.fn() }));

const reply = (payload, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: vi.fn().mockResolvedValue(payload),
});

const htmlReply = (status) => ({
  ok: false,
  status,
  json: vi.fn().mockRejectedValue(new SyntaxError("Unexpected token <")),
});

describe("authApi", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it("returns a verified authenticated session", async () => {
    const session = { authenticated: true, user: { email: "operator@example.com", role: "operator" }, session: { active: true } };
    apiFetch.mockResolvedValue(reply(session));

    await expect(fetchCurrentUser()).resolves.toEqual(session);
  });

  it("treats no active session as a normal signed-out state without trusting localStorage", async () => {
    window.localStorage.setItem("neraium.local_auth.session", "operator@example.com");
    apiFetch.mockResolvedValue(reply({ authenticated: false, user: null, session: null }));

    await expect(fetchCurrentUser()).resolves.toEqual({
      authenticated: false,
      user: null,
      session: null,
    });
  });

  it("treats a 401 session response as signed out", async () => {
    apiFetch.mockResolvedValue(reply({ detail: "expired" }, 401));

    await expect(fetchCurrentUser()).resolves.toEqual({ authenticated: false, user: null, session: null });
  });

  it("reports session backend failures separately from no active session", async () => {
    apiFetch.mockResolvedValue(htmlReply(503));

    await expect(fetchCurrentUser()).rejects.toMatchObject({
      name: "SessionInitializationError",
      kind: SESSION_INITIALIZATION_ERROR_KIND.BACKEND_UNAVAILABLE,
    });
  });

  it("classifies network failure as backend unavailable", async () => {
    apiFetch.mockRejectedValue(new TypeError("offline"));

    await expect(fetchCurrentUser()).rejects.toMatchObject({
      kind: SESSION_INITIALIZATION_ERROR_KIND.BACKEND_UNAVAILABLE,
    });
  });

  it("classifies an API timeout separately", async () => {
    apiFetch.mockRejectedValue(Object.assign(new Error("slow"), { name: "ApiTimeoutError" }));

    await expect(fetchCurrentUser()).rejects.toMatchObject({
      kind: SESSION_INITIALIZATION_ERROR_KIND.TIMEOUT,
    });
  });

  it("enforces a total session initialization deadline", async () => {
    vi.useFakeTimers();
    apiFetch.mockImplementation(() => new Promise(() => {}));

    const sessionRequest = fetchCurrentUser({ timeoutMs: 50 });
    const rejection = expect(sessionRequest).rejects.toMatchObject({ kind: SESSION_INITIALIZATION_ERROR_KIND.TIMEOUT });
    await vi.advanceTimersByTimeAsync(50);

    await rejection;
    vi.useRealTimers();
  });

  it("rejects malformed JSON from a successful route", async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockRejectedValue(new SyntaxError("Unexpected token <")),
    });

    await expect(fetchCurrentUser()).rejects.toMatchObject({
      kind: SESSION_INITIALIZATION_ERROR_KIND.MALFORMED_RESPONSE,
    });
  });

  it("rejects JSON that does not contain an authentication decision", async () => {
    apiFetch.mockResolvedValue(reply({ user: null }));

    await expect(fetchCurrentUser()).rejects.toMatchObject({
      kind: SESSION_INITIALIZATION_ERROR_KIND.MALFORMED_RESPONSE,
    });
  });

  it("aborts the underlying API request when the caller unmounts", async () => {
    apiFetch.mockImplementation((_path, options) => new Promise((resolve, reject) => {
      options.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
      void resolve;
    }));
    const controller = new AbortController();

    const sessionRequest = fetchCurrentUser({ signal: controller.signal });
    controller.abort();

    await expect(sessionRequest).rejects.toMatchObject({ name: "AbortError" });
    expect(apiFetch.mock.calls[0][1].signal.aborted).toBe(true);
  });

  it("keeps invalid credentials specific to a 401 response", async () => {
    apiFetch.mockResolvedValue(reply({ detail: "Invalid email or password." }, 401));

    await expect(loginUser({ email: "Craig@neraium.com", password: "wrong-password" }))
      .rejects.toThrow("Invalid email or password.");
  });

  it("does not convert a non-JSON backend failure into invalid credentials", async () => {
    apiFetch.mockResolvedValue(htmlReply(503));

    await expect(loginUser({ email: "Craig@neraium.com", password: "password123" }))
      .rejects.toThrow(/sign-in service is temporarily unavailable/i);
  });

  it("does not convert a network failure into invalid credentials", async () => {
    apiFetch.mockRejectedValue(new Error("offline"));

    await expect(loginUser({ email: "Craig@neraium.com", password: "password123" }))
      .rejects.toThrow(/sign-in service is temporarily unavailable/i);
  });

  it("clears the local marker after the server revokes the session", async () => {
    window.localStorage.setItem("neraium.local_auth.session", "operator@example.com");
    apiFetch.mockResolvedValue(reply({ authenticated: false }));

    await expect(logoutUser()).resolves.toEqual({ authenticated: false });
    expect(window.localStorage.getItem("neraium.local_auth.session")).toBeNull();
  });

  it("keeps local state consistent when the server cannot revoke the session", async () => {
    window.localStorage.setItem("neraium.local_auth.session", "operator@example.com");
    apiFetch.mockRejectedValue(new Error("offline"));

    await expect(logoutUser()).rejects.toThrow(/sign-out service is unavailable/i);
    expect(window.localStorage.getItem("neraium.local_auth.session")).toBe("operator@example.com");
  });
});
