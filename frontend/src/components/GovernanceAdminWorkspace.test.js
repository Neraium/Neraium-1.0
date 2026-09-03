/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import GovernanceAdminWorkspace from "./GovernanceAdminWorkspace";

const h = React.createElement;
const reply = (payload) => ({ ok: true, status: 200, json: async () => payload });
const Panel = ({ title, subtitle, children }) => h("section", {}, h("h2", {}, title), subtitle ? h("p", {}, subtitle) : null, children);
const EmptyState = ({ title, body }) => h("section", {}, h("h2", {}, title), h("p", {}, body));

afterEach(() => { cleanup(); window.sessionStorage.clear(); vi.clearAllMocks(); });

it("retires the legacy telemetry connector setup from the administrator workspace", async () => {
  const apiFetch = vi.fn(async (path) => {
    if (path.startsWith("/api/observability/evp-governance")) return reply({ records: [], total: 0, pass_count: 0, no_pass_count: 0 });
    if (path.startsWith("/api/observability/performance")) return reply({ queue_depth: 0, upload_duration_seconds: {}, cache: {} });
    if (path.startsWith("/api/auth/users")) return reply({ users: [] });
    if (path.startsWith("/api/auth/sessions")) return reply({ sessions: [] });
    if (path === "/api/auth/invitations") return reply({ invitations: [] });
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

  expect(await screen.findByRole("heading", { name: "Access & governance" })).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "Telemetry Connector Setup" })).toBeNull();
  expect(apiFetch).not.toHaveBeenCalledWith("/api/connectors/types", expect.anything());
  expect(apiFetch).not.toHaveBeenCalledWith("/api/connectors/health", expect.anything());
});

it("manages current facility membership separately from account status", async () => {
  const apiFetch = vi.fn(async (path, options = {}) => {
    if (path.startsWith("/api/observability/evp-governance")) return reply({ records: [], total: 0, pass_count: 0, no_pass_count: 0 });
    if (path.startsWith("/api/observability/performance")) return reply({ queue_depth: 0, upload_duration_seconds: {}, cache: {} });
    if (path.startsWith("/api/auth/users")) return reply({ users: [
      { email: "admin@neraium.test", name: "Admin", role: "admin", is_active: true },
      { email: "tech@neraium.test", name: "Taylor Tech", role: "viewer", is_active: true },
      { email: "candidate@neraium.test", name: "Casey Candidate", role: "operator", is_active: true },
      { email: "inactive@neraium.test", name: "Inactive", role: "viewer", is_active: false },
    ] });
    if (path.startsWith("/api/auth/sessions")) return reply({ sessions: [] });
    if (path === "/api/auth/invitations") return reply({ invitations: [] });
    if (path === "/api/workspaces/current/members") return reply({ workspace_id: "ws-central", members: [
      { member_id: "admin@neraium.test", display_name: "Admin", role: "admin", is_active: true },
      { member_id: "tech@neraium.test", display_name: "Taylor Tech", role: "viewer", is_active: true },
    ] });
    if (path === "/api/connectors/types") return reply({ types: [] });
    if (path === "/api/connectors/health") return reply({ connectors: [] });
    if (options.method === "POST") return reply({ message: "Workspace access updated." });
    throw new Error(`Unexpected request: ${path}`);
  });

  render(h(GovernanceAdminWorkspace, {
    apiFetch,
    accessCode: "",
    Panel,
    EmptyState,
    currentUser: { email: "admin@neraium.test", role: "admin" },
    currentWorkspace: { workspace_id: "ws-central", display_name: "Central Plant", kind: "facility" },
  }));

  expect(await screen.findByRole("heading", { name: "Current facility membership" })).toBeTruthy();
  expect(screen.getByText(/access is separate from global account status/i)).toBeTruthy();
  const accountSelect = screen.getByLabelText("Account to add to current facility");
  await waitFor(() => expect(Array.from(accountSelect.options).map((option) => option.value)).toEqual(["", "candidate@neraium.test"]));
  fireEvent.change(accountSelect, { target: { value: "candidate@neraium.test" } });
  fireEvent.click(screen.getByRole("button", { name: "Add facility access" }));
  await waitFor(() => expect(apiFetch).toHaveBeenCalledWith(
    "/api/workspaces/ws-central/members",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ email: "candidate@neraium.test" }) }),
  ));

  fireEvent.click(screen.getAllByRole("button", { name: "Disable facility access" }).find((button) => !button.disabled));
  await waitFor(() => expect(apiFetch).toHaveBeenCalledWith(
    "/api/workspaces/ws-central/members/tech%40neraium.test/disable",
    expect.objectContaining({ method: "POST" }),
  ));
  expect(screen.getAllByText(/account active/i).length).toBeGreaterThan(0);
});

it("creates a reusable company signup link without a selected facility", async () => {
  const token = "company-signup-link-token-abcdefghijklmnopqrstuvwxyz";
  const apiFetch = vi.fn(async (path, options = {}) => {
    if (path.startsWith("/api/observability/evp-governance")) return reply({ records: [], total: 0, pass_count: 0, no_pass_count: 0 });
    if (path.startsWith("/api/observability/performance")) return reply({ queue_depth: 0, upload_duration_seconds: {}, cache: {} });
    if (path.startsWith("/api/auth/users")) return reply({ users: [] });
    if (path.startsWith("/api/auth/sessions")) return reply({ sessions: [] });
    if (path === "/api/auth/invitations" && options.method === "POST") return reply({ invite_id: "ei-test", invite_token: token });
    if (path === "/api/auth/invitations") return reply({ invitations: [] });
    throw new Error(`Unexpected request: ${path}`);
  });
  render(h(GovernanceAdminWorkspace, {
    apiFetch, accessCode: "", Panel, EmptyState,
    currentUser: { email: "admin@neraium.test", role: "admin" },
    currentWorkspace: { workspace_id: "default", display_name: "Personal workspace", kind: "personal" },
  }));

  fireEvent.click(await screen.findByRole("button", { name: "Create invite link" }));
  await waitFor(() => expect(apiFetch).toHaveBeenCalledWith(
    "/api/auth/invitations", expect.objectContaining({ method: "POST" }),
  ));
  expect(screen.getByDisplayValue(`${window.location.origin}/#invite=${encodeURIComponent(token)}`)).toBeTruthy();
});
