/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AuthScreen from "./AuthScreen";
import { loginUser } from "../services/api/authApi";

const h = React.createElement;

vi.mock("../services/api/authApi", () => ({ loginUser: vi.fn() }));

afterEach(() => { cleanup(); vi.clearAllMocks(); window.localStorage.clear(); });

describe("AuthScreen", () => {
  it("shows actionable validation and prevents duplicate sign-in submissions", async () => {
    let resolveLogin;
    loginUser.mockReturnValue(new Promise((resolve) => { resolveLogin = resolve; }));
    const onAuthenticated = vi.fn();
    render(h(AuthScreen, { notice: "Your session expired. Sign in again to continue.", onAuthenticated }));

    expect(screen.getByText("Neraium")).toBeTruthy();
    expect(screen.getByText("Systemic Infrastructure Intelligence")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Welcome back" })).toBeTruthy();
    expect(screen.getByText("Sign in to continue.")).toBeTruthy();
    expect(screen.queryByText(/See the behavior behind the system\./i)).toBeNull();
    expect(screen.queryByText(/decision environment/i)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByRole("alert").textContent).toContain("email and password");
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "admin@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByRole("button", { name: "Signing in..." }).disabled).toBe(true);
    expect(loginUser).toHaveBeenCalledTimes(1);
    resolveLogin({ user: { email: "admin@example.com", role: "admin" } });
    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledTimes(1));
  });
});
