/* @vitest-environment jsdom */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RelatedEvidencePackages from "./RelatedEvidencePackages";

describe("RelatedEvidencePackages", () => {
  it("keeps the selected package separate and renders reasons and references", async () => {
    const apiFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        correlation_status: "related_packages_found",
        limitations: [],
        related_packages: [{
          relationship_id: "relationship-1",
          package_id: "package-b",
          strongest_supported_relationship: "overlapping_observation_window",
          supporting_relationships: ["overlapping_observation_window", "same_system"],
          evidence_refs: ["evidence-package:package-a#system_id"],
          limitations: [],
        }],
      }),
    });

    render(React.createElement(RelatedEvidencePackages, { packageId: "package-a", apiFetch }));

    await waitFor(() => expect(screen.getByRole("heading", { name: "Related findings observed" })).toBeTruthy());
    expect(screen.getByText("Selected package").parentElement.textContent).toContain("package-a");
    expect(screen.getByRole("heading", { name: /Related package package-b/ })).toBeTruthy();
    expect(screen.getByText(/overlapping observation windows/)).toBeTruthy();
    expect(screen.getByText("Related evidence does not establish cause, propagation, diagnosis, or equipment failure.")).toBeTruthy();
  });

  it("does not issue a request when no current package identity exists", () => {
    const apiFetch = vi.fn();
    render(React.createElement(RelatedEvidencePackages, { packageId: "", apiFetch }));
    expect(screen.getByRole("heading", { name: "Related findings unavailable" })).toBeTruthy();
    expect(screen.getByText(/No persisted Evidence Package identity/)).toBeTruthy();
    expect(apiFetch).not.toHaveBeenCalled();
  });
});
