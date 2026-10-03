/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AppErrorBoundary, { isChunkLoadError } from "./AppErrorBoundary";

function BrokenWorkspace({ message }) {
  throw new Error(message);
}

describe("AppErrorBoundary", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("recognizes browser lazy-import failures", () => {
    expect(isChunkLoadError(new TypeError("Failed to fetch dynamically imported module: /assets/workspace-123.js"))).toBe(true);
    expect(isChunkLoadError(new Error("Importing a module script failed."))).toBe(true);
    expect(isChunkLoadError(new Error("telemetry render failed"))).toBe(false);
  });

  it("offers generic retry without promising an unsupported saved-state recovery", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const onRetry = vi.fn();
    render(React.createElement(AppErrorBoundary, { onRetry }, React.createElement(BrokenWorkspace, { message: "render failed" })));
    expect(screen.queryByRole("button", { name: "Use last available state" })).toBeNull();
    expect(screen.queryByText(/existing analysis are still available/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry workspace" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("offers saved-state recovery only when supplied, and never for a failed chunk", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const onUseLastAvailableState = vi.fn();
    const { unmount } = render(React.createElement(AppErrorBoundary, { onUseLastAvailableState }, React.createElement(BrokenWorkspace, { message: "render failed" })));
    fireEvent.click(screen.getByRole("button", { name: "Use last available state" }));
    expect(onUseLastAvailableState).toHaveBeenCalledTimes(1);
    unmount();
    render(React.createElement(AppErrorBoundary, { onUseLastAvailableState, reloadPage: vi.fn() }, React.createElement(BrokenWorkspace, { message: "Error loading dynamically imported module" })));
    expect(screen.queryByRole("button", { name: "Use last available state" })).toBeNull();
    expect(screen.getByRole("button", { name: "Reload Workspace" })).toBeTruthy();
  });

  it("reloads once automatically when a deployed lazy chunk is no longer available", () => {
    const reloadPage = vi.fn();
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    render(React.createElement(
      AppErrorBoundary,
      { reloadPage },
      React.createElement(BrokenWorkspace, { message: "Failed to fetch dynamically imported module: /assets/workspace-old.js" }),
    ));

    expect(reloadPage).toHaveBeenCalledTimes(1);
    expect(screen.getByText("The workspace was updated")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reload Workspace" })).toBeTruthy();
    consoleError.mockRestore();
  });

  it("uses a hard reload instead of retrying the cached rejected import", () => {
    const reloadPage = vi.fn();
    const onRetry = vi.fn();
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    render(React.createElement(
      AppErrorBoundary,
      { reloadPage, onRetry },
      React.createElement(BrokenWorkspace, { message: "Error loading dynamically imported module" }),
    ));
    fireEvent.click(screen.getByRole("button", { name: "Reload Workspace" }));

    expect(reloadPage).toHaveBeenCalledTimes(2);
    expect(onRetry).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });
});
