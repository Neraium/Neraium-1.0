import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import WorkspaceShell from "./WorkspaceShell";

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("shared workspace navigation", () => {
  it("uses existing destinations and keeps Administration limited to admins", () => {
    const onNavigate = vi.fn();
    const { rerender } = render(React.createElement(WorkspaceShell, { activeNavigation: "help-changelog", onNavigate, currentUser: { role: "operator" } }));
    const nav = screen.getByRole("navigation", { name: "Primary navigation" });
    expect(within(nav).queryByRole("button", { name: "Administration" })).toBeNull();
    expect(within(nav).getByRole("button", { name: "Help & Status" }).getAttribute("aria-current")).toBe("page");
    for (const [label, target] of [["Analysis Findings", "findings"], ["Historical review", "observation-center"], ["Historical replay", "system-story"]]) {
      fireEvent.click(within(nav).getByRole("button", { name: label }));
      expect(onNavigate).toHaveBeenLastCalledWith(target);
    }
    rerender(React.createElement(WorkspaceShell, { onNavigate, currentUser: { role: "admin" } }));
    expect(within(nav).getByRole("button", { name: "Administration" })).toBeTruthy();
  });

  it("preserves mobile menu focus, Escape and body-scroll restoration", () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
    render(React.createElement(WorkspaceShell, { activeNavigation: "data-connections", onNavigate: vi.fn() }));
    const menu = screen.getByRole("button", { name: "Open menu" });
    fireEvent.click(menu);
    expect(document.activeElement.textContent).toBe("Data");
    expect(document.body.style.overflow).toBe("hidden");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.activeElement).toBe(menu);
    expect(menu.getAttribute("aria-expanded")).toBe("false");
    expect(document.body.style.overflow).toBe("");
    vi.unstubAllGlobals();
  });
});
