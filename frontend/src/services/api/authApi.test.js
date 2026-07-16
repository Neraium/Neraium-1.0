/* @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../../config";
import { logoutUser } from "./authApi";

vi.mock("../../config", () => ({ apiFetch: vi.fn() }));

const reply = (payload, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: vi.fn().mockResolvedValue(payload),
});

describe("logoutUser", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.setItem("neraium.local_auth.session", "operator@example.com");
  });

  it("clears the local marker after the server revokes the session", async () => {
    apiFetch.mockResolvedValue(reply({ authenticated: false }));
    await expect(logoutUser()).resolves.toEqual({ authenticated: false });
    expect(window.localStorage.getItem("neraium.local_auth.session")).toBeNull();
  });

  it("keeps local state consistent when the server cannot revoke the session", async () => {
    apiFetch.mockRejectedValue(new Error("offline"));
    await expect(logoutUser()).rejects.toThrow(/sign-out service is unavailable/i);
    expect(window.localStorage.getItem("neraium.local_auth.session")).toBe("operator@example.com");
  });
});
