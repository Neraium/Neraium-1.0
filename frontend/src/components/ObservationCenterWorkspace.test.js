/* @vitest-environment jsdom */
import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ObservationCenterWorkspace from "./ObservationCenterWorkspace";

const h = React.createElement;

vi.mock("./workspacePrimitives", () => ({
  EmptyState: ({ title, body }) => h("div", { "data-testid": "empty-state" }, h("strong", null, title), h("p", null, body)),
  MetricGrid: ({ metrics }) => h("div", { "data-testid": "metric-grid" }, metrics?.map((metric) => h("div", { key: metric.label }, `${metric.label}:${metric.value}`))),
  Panel: ({ title, children }) => h("section", { "data-testid": title }, h("h2", null, title), children),
}));

vi.mock("./HealthOrb", () => ({ default: () => h("div", { "data-testid": "health-orb" }) }));

function createResponse(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  };
}

function renderWorkspace(apiFetch = vi.fn()) {
  return render(h(ObservationCenterWorkspace, { apiFetch, accessCode: "" }));
}

function installLocalStorageMock() {
  const store = new Map();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => {
        store.set(String(key), String(value));
      },
      removeItem: (key) => {
        store.delete(String(key));
      },
      clear: () => {
        store.clear();
      },
    },
  });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ObservationCenterWorkspace", () => {

  it("explains the zero-observation state without showing a fallback regime", async () => {
    installLocalStorageMock();
    const apiFetch = vi.fn(async (path) => {
      if (String(path) === "/api/evidence/runs") {
        return createResponse({ runs: [] });
      }
      return createResponse({}, 404);
    });

    renderWorkspace(apiFetch);

    await waitFor(() => {
      expect(screen.getByText(/no structural observations have been recorded yet/i)).toBeTruthy();
    });

    expect(screen.getByText(/the instrument is quiet because no reviewable structural changes have been recorded/i)).toBeTruthy();
    expect(screen.getByText(/Current regime:No observations recorded/i)).toBeTruthy();
    expect(screen.queryByText(/State Group A/i)).toBeNull();
  });
  it("renders backend historical fact text from the evidence API", async () => {
    installLocalStorageMock();
    const apiFetch = vi.fn(async (path) => {
      if (String(path) === "/api/evidence/runs") {
        return createResponse({
          runs: [
            {
              run_id: "followup-run",
              source_name: "followup.csv",
              source_type: "csv_upload",
              status: "completed",
              created_at: "2026-05-02T08:00:00Z",
              completed_at: "2026-05-02T08:01:00Z",
              observation_type: "coupling_change",
              observation_status: "open",
              regime_label: "State Group A",
              structural_state: "Monitoring",
              variables: ["temperature", "humidity"],
              drift_metrics: { baseline_distance: 0.91 },
              evidence_summary: ["Follow-up structural drift observed."],
              data_conditions: [],
              historical_fact: "Similar coupling change observations involving temperature and humidity were later marked known operational change in 1 of 1 previous investigations.",
            },
          ],
        });
      }
      return createResponse({}, 404);
    });

    renderWorkspace(apiFetch);

    await waitFor(() => {
      expect(screen.getByText(/similar coupling change observations involving temperature and humidity/i)).toBeTruthy();
    });
  });
});
