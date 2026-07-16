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
  it("renders an awaiting behavior baseline without hotspots", () => {
    render(h(OperationalOrb, { status: "awaiting" }));

    const orb = screen.getByTestId("operational-orb");
    expect(orb.getAttribute("data-status")).toBe("awaiting");
    expect(orb.getAttribute("aria-label")).toContain("Awaiting Operational Baseline");
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
    render(h(OperationalOrb, {
      state: {
        key: "behavior-change",
        label: "Relationship Drift Detected",
        hotspotCount: 3,
        changedSystems: ["Water Quality", "Pump system", "Electrical"],
      },
    }));

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

  it("renders all meaningful supplied hotspots when hotspotCount is omitted", () => {
    render(h(OperationalOrb, {
      status: "warning",
      hotspots: [
        {
          x: 24,
          y: 42,
          scale: 0.9,
          subsystem: "Pump system",
        },
        {
          x: 68,
          y: 58,
          scale: 1.1,
          subsystem: "Filtration",
        },
      ],
    }));
    const orb = screen.getByTestId("operational-orb");
    const hotspots = orb.querySelectorAll(
      ".operational-orb__hotspot"
    );
    expect(hotspots).toHaveLength(2);
    expect(
      hotspots[0].style.getPropertyValue("--hotspot-x")
    ).toBe("24%");
  });

  it("renders all resolved changed-family hotspots when hotspotCount is omitted", () => {
    render(h(OperationalOrb, {
      status: "elevated",
      state: {
        ridgeActivity: [
          "Pump system",
          "Flow pressure differential",
        ],
      },
    }));
    const orb = screen.getByTestId("operational-orb");
    expect(
      orb.querySelectorAll(".operational-orb__hotspot")
    ).toHaveLength(2);
  });

  it("limits supplied hotspots when hotspotCount is positive", () => {
    render(h(OperationalOrb, {
      status: "warning",
      hotspotCount: 1,
      hotspots: [
        {
          x: 24,
          y: 42,
          scale: 0.9,
          subsystem: "Pump system",
        },
        {
          x: 68,
          y: 58,
          scale: 1.1,
          subsystem: "Filtration",
        },
      ],
    }));
    const orb = screen.getByTestId("operational-orb");
    expect(
      orb.querySelectorAll(".operational-orb__hotspot")
    ).toHaveLength(1);
  });

  it("honors an explicit zero hotspot count", () => {
    render(h(OperationalOrb, {
      status: "warning",
      hotspotCount: 0,
      hotspots: [
        {
          x: 24,
          y: 42,
          scale: 0.9,
          subsystem: "Pump system",
        },
      ],
    }));
    const orb = screen.getByTestId("operational-orb");
    expect(
      orb.querySelectorAll(".operational-orb__hotspot")
    ).toHaveLength(0);
  });

  it("renders the active fingerprint when counts are omitted", () => {
    render(h(OperationalOrb, {
      status: "healthy",
    }));
    const orb = screen.getByTestId("operational-orb");
    expect(
      orb.querySelectorAll(
        ".operational-orb__fingerprint path.is-active"
      )
    ).toHaveLength(10);
  });

  it("activates changed high-confidence ridges during early states", () => {
    render(h(OperationalOrb, {
      status: "learning",
      state: {
        changedSystems: ["Electrical"],
      },
    }));
    const orb = screen.getByTestId("operational-orb");
    const changedRidges = orb.querySelectorAll(
      '.operational-orb__fingerprint path[data-system="electrical"].is-changed'
    );
    expect(changedRidges.length).toBeGreaterThan(0);
    changedRidges.forEach((ridge) => {
      expect(ridge.classList.contains("is-active")).toBe(true);
    });
  });
});
