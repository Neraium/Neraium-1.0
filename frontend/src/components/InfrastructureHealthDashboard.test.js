import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import InfrastructureHealthDashboard from "./InfrastructureHealthDashboard";

function Panel({ title, subtitle, children }) {
  return React.createElement("section", null, React.createElement("h2", null, title), React.createElement("p", null, subtitle), children);
}

const healthyPayload = {
  overall_status: "healthy",
  category: "Infrastructure Healthy",
  observed_at: "2026-07-25T12:00:00+00:00",
  confidence: "high",
  current_alerts: [],
  pending_validation: [],
  incidents: [],
  subsystems: {
    api: { status: "healthy", evidence: ["ALB reports 1/1 healthy API target."], checks: { api_latency: { latency_ms: 125 } } },
    auth: { status: "healthy", evidence: ["Authentication database connectivity probe completed."], checks: { auth_connectivity: { status: "healthy", latency_ms: 42 } } },
    runtime_db: { status: "healthy", evidence: ["Runtime database connectivity probe completed."], checks: { runtime_db_connectivity: { status: "healthy" } } },
    workers: { status: "healthy", evidence: ["Worker heartbeat is 20 seconds old."], checks: { worker_heartbeat: { status: "healthy", metadata: { age_seconds: 20 } } } },
    uploads: { status: "healthy", evidence: ["No queue stall threshold is exceeded."], checks: {} },
    notifications: { status: "healthy", evidence: ["Configured notification adapters: console, sns."], checks: {} },
    storage: { status: "healthy", evidence: ["Runtime directory write probe succeeded."], checks: {} },
    secrets: {
      status: "healthy",
      evidence: ["Secrets Manager metadata probe completed."],
      checks: {
        credential_refresh: { metadata: { last_refresh_success_at: "2026-07-25T11:59:00+00:00" } },
        secrets_manager_access: { metadata: { age_seconds: 3600 } },
      },
    },
  },
};

it("renders a quiet complete production health dashboard", async () => {
  const apiFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => healthyPayload });

  const { unmount } = render(React.createElement(InfrastructureHealthDashboard, { apiFetch, accessCode: "", Panel }));

  await waitFor(() => expect(screen.getByRole("heading", { name: "Infrastructure Healthy" })).toBeTruthy());
  expect(screen.getByText(/All monitored production subsystems/)).toBeTruthy();
  expect(screen.getByText("Authentication database connectivity probe completed.")).toBeTruthy();
  expect(screen.getByText("Worker heartbeat is 20 seconds old.")).toBeTruthy();
  expect(screen.getByText("No persistent infrastructure incidents have been recorded.")).toBeTruthy();
  expect(apiFetch).toHaveBeenCalledWith("/api/infrastructure/health?incident_limit=50", expect.objectContaining({ cache: "no-store" }));
  unmount();
});

it("surfaces active alerts and the recommended first check", async () => {
  const degradedPayload = {
    ...healthyPayload,
    overall_status: "critical",
    category: "Infrastructure Critical",
    current_alerts: [{
      incident_id: "auth_connectivity:1",
      category: "Infrastructure Critical",
      severity: "critical",
      subsystem: "auth",
      started_at: "2026-07-25T11:55:00+00:00",
      impact: "Users cannot authenticate.",
      recommended_first_check: "Verify RDS credentials and Secrets Manager rotation.",
    }],
    incidents: [],
  };
  const apiFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => degradedPayload });

  const { unmount } = render(React.createElement(InfrastructureHealthDashboard, { apiFetch, accessCode: "", Panel }));

  await waitFor(() => expect(screen.getByRole("heading", { name: "Infrastructure Critical" })).toBeTruthy());
  expect(screen.getByText("Users cannot authenticate.")).toBeTruthy();
  expect(screen.getByText(/Verify RDS credentials and Secrets Manager rotation/)).toBeTruthy();
  unmount();
});
