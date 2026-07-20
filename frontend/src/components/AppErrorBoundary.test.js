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
