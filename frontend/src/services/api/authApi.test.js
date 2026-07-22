/* @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../../config";
import { fetchCurrentUser, loginUser, logoutUser } from "./authApi";

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
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it("treats no active session as a normal signed-out state", async () => {
    apiFetch.mockResolvedValue(reply({ authenticated: false, user: null, session: null }));

    await expect(fetchCurrentUser()).resolves.toEqual({
      authenticated: false,
      user: null,
      session: null,
    });
  });

  it("reports session backend failures separately from no active session", async () => {
    apiFetch.mockResolvedValue(htmlReply(503));

    await expect(fetchCurrentUser()).rejects.toThrow(/session service is temporarily unavailable/i);
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
