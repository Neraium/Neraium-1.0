/* @vitest-environment jsdom */
import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import GovernanceAdminWorkspace from "./GovernanceAdminWorkspace";

const h = React.createElement;
const reply = (payload) => ({ ok: true, status: 200, json: async () => payload });
const Panel = ({ title, subtitle, children }) => h("section", {}, h("h2", {}, title), subtitle ? h("p", {}, subtitle) : null, children);
const EmptyState = ({ title, body }) => h("section", {}, h("h2", {}, title), h("p", {}, body));

afterEach(() => { cleanup(); window.sessionStorage.clear(); vi.clearAllMocks(); });

it("hosts telemetry connector setup in the administrator workspace", async () => {
  const apiFetch = vi.fn(async (path) => {
    if (path.startsWith("/api/observability/evp-governance")) return reply({ records: [], total: 0, pass_count: 0, no_pass_count: 0 });
    if (path.startsWith("/api/observability/performance")) return reply({ queue_depth: 0, upload_duration_seconds: {}, cache: {} });
    if (path.startsWith("/api/auth/users")) return reply({ users: [] });
    if (path.startsWith("/api/auth/sessions")) return reply({ sessions: [] });
    if (path === "/api/connectors/types") return reply({ types: [{ connector_type: "rest", display_name: "REST API", functional: true }] });
    if (path === "/api/connectors/health") return reply({ connectors: [] });
    throw new Error(`Unexpected request: ${path}`);
  });

  render(h(GovernanceAdminWorkspace, {
    apiFetch,
    accessCode: "",
    Panel,
    EmptyState,
    currentUser: { email: "admin@neraium.test", role: "admin" },
  }));

  expect(await screen.findByRole("heading", { name: "Telemetry Connector Setup" })).toBeTruthy();
  await waitFor(() => expect(screen.getByRole("button", { name: "Test connection" }).disabled).toBe(false));
  expect(screen.getByLabelText("Connector type")).toBeTruthy();
  expect(screen.getByLabelText("Source identifier")).toBeTruthy();
  expect(screen.getByLabelText("System identifier")).toBeTruthy();
  expect(screen.getByLabelText("Endpoint")).toBeTruthy();
  expect(screen.getByLabelText("Sample response JSON")).toBeTruthy();
});
