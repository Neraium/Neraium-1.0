/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ConnectorSetupPanel from "./ConnectorSetupPanel";

const h = React.createElement;

const reply = (payload, status = 200) => ({ ok: status >= 200 && status < 300, status, json: vi.fn().mockResolvedValue(payload) });

afterEach(() => { cleanup(); window.sessionStorage.clear(); vi.clearAllMocks(); });

describe("ConnectorSetupPanel", () => {
  it("renders nothing for non-administrators and does not call admin endpoints", () => {
    const apiFetch = vi.fn();
    const { container } = render(h(ConnectorSetupPanel, { apiFetch, currentUser: { role: "operator" } }));
    expect(container.innerHTML).toBe("");
    expect(screen.queryByRole("heading", { name: /Telemetry connector/i })).toBeNull();
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("tests a REST sample once, reports success, and refreshes health", async () => {
    const apiFetch = vi.fn(async (path) => {
      if (path === "/api/connectors/types") return reply({ types: [{ connector_type: "rest", display_name: "REST API", functional: true }, { connector_type: "database", display_name: "Database", functional: true }] });
      if (path === "/api/connectors/health") return reply({ connectors: [{ connector_type: "rest", display_name: "REST API", connection_status: "ready", records_ingested: 1, sensors_detected: 1, errors: [] }] });
      if (path === "/api/connectors/rest/test") return reply({ message: "REST connector validated.", records_ingested: 0 });
      throw new Error(`unexpected ${path}`);
    });
    render(h(ConnectorSetupPanel, { apiFetch, currentUser: { role: "admin" } }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Test connection" }).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }));
    await screen.findByText(/No records were saved/i);
    expect(apiFetch.mock.calls.filter(([path]) => path === "/api/connectors/rest/test")).toHaveLength(1);
  });

  it("turns a connector validation failure into a next-step message", async () => {
    const apiFetch = vi.fn(async (path) => {
      if (path === "/api/connectors/types") return reply({ types: [{ connector_type: "rest", display_name: "REST API", functional: true }] });
      if (path === "/api/connectors/health") return reply({ connectors: [] });
      if (path === "/api/connectors/rest/test") return reply({ detail: "Sample payload requires timestamp, sensor_id, and value fields." }, 400);
      throw new Error(`unexpected ${path}`);
    });
    render(h(ConnectorSetupPanel, { apiFetch, currentUser: { role: "admin" } }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Test connection" }).disabled).toBe(false));
    fireEvent.change(screen.getByLabelText("Sample response JSON"), { target: { value: JSON.stringify({ records: [{}] }) } });
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Review the fields and retry");
  });
});
