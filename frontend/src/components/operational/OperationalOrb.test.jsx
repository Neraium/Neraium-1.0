/* @vitest-environment jsdom */
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import OperationalOrb from "./OperationalOrb";

const h = React.createElement;

afterEach(() => {
  cleanup();
});

describe("OperationalOrb", () => {
  it("renders an awaiting Operational Fingerprint without hotspots", () => {
    render(h(OperationalOrb, { status: "awaiting" }));

    const orb = screen.getByTestId("operational-orb");
    expect(orb.getAttribute("data-status")).toBe("awaiting");
    expect(orb.getAttribute("aria-label")).toContain("Awaiting Operational Fingerprint");
    expect(orb.querySelectorAll(".operational-orb__hotspot")).toHaveLength(0);
  });

  it("renders configurable drift hotspots without changing the teal base status", () => {
    render(h(OperationalOrb, {
      status: "warning",
      hotspotCount: 2,
      hotspots: [
        { x: 24, y: 42, scale: 0.9, subsystem: "Pump system" },
        { x: 68, y: 58, scale: 1.1, subsystem: "Filtration" },
      ],
    }));

    const orb = screen.getByTestId("operational-orb");
    const hotspots = orb.querySelectorAll(".operational-orb__hotspot");
    expect(orb.getAttribute("data-status")).toBe("warning");
    expect(hotspots).toHaveLength(2);
    expect(hotspots[0].style.getPropertyValue("--hotspot-x")).toBe("24%");
    expect(hotspots[0].getAttribute("title")).toBe("Pump system");
  });

  it("keeps compatibility with the existing state object contract", () => {
    render(h(OperationalOrb, { state: { key: "behavior-change", label: "Relationship Drift Detected", hotspotCount: 3 } }));

    const orb = screen.getByTestId("operational-orb");
    expect(orb.getAttribute("data-status")).toBe("warning");
    expect(orb.querySelectorAll(".operational-orb__hotspot")).toHaveLength(3);
  });

  it("maps affected operational systems to changed fingerprint ridges", () => {
    render(h(OperationalOrb, {
      status: "warning",
      state: {
        label: "Water quality drift",
        ridgeActivity: ["Water Quality", "pH dosing relationship"],
      },
    }));

    const orb = screen.getByTestId("operational-orb");
    const changedRidges = Array.from(orb.querySelectorAll(".operational-orb__fingerprint path.is-changed"));
    expect(changedRidges.length).toBeGreaterThan(0);
    expect(changedRidges.every((ridge) => ridge.getAttribute("data-system") === "water-quality")).toBe(true);
    expect(orb.querySelectorAll(".operational-orb__ridge-particle[data-system='water-quality']").length).toBeGreaterThan(0);
  });
});
