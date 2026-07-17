/* @vitest-environment jsdom */
import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "./workspacePrimitives";

const h = React.createElement;

describe("EmptyState", () => {
  it("preserves actionable unavailable-state copy", () => {
    render(h(EmptyState, {
      title: "Insights Unavailable",
      body: "The analysis service is unavailable. Check service health and retry.",
    }));

    expect(screen.getByText("Insights Unavailable")).toBeTruthy();
    expect(screen.getByText("The analysis service is unavailable. Check service health and retry.")).toBeTruthy();
  });
});