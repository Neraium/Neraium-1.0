/* @vitest-environment jsdom */
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import FacilityFingerprintMark from "./FacilityFingerprintMark";

const h = React.createElement;

afterEach(() => {
  cleanup();
});

describe("FacilityFingerprintMark", () => {
  it("renders the shared engineered fingerprint as a facility identity mark", () => {
    render(h(FacilityFingerprintMark, { status: "healthy", label: "Facility mark" }));

    const mark = screen.getByRole("img", { name: "Facility mark" });
    expect(mark.getAttribute("data-status")).toBe("healthy");
    expect(mark.querySelectorAll("path").length).toBeGreaterThan(8);
  });

  it("highlights only affected ridge families", () => {
    render(h(FacilityFingerprintMark, {
      status: "warning",
      state: { ridgeActivity: ["Water Quality", "pH dosing relationship"] },
      label: "Changed mark",
    }));

    const mark = screen.getByRole("img", { name: "Changed mark" });
    const changedRidges = Array.from(mark.querySelectorAll("path.is-changed"));
    expect(changedRidges.length).toBeGreaterThan(0);
    expect(changedRidges.every((ridge) => ridge.getAttribute("data-system") === "water-quality")).toBe(true);
  });
});
