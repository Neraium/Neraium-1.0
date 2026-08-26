import React from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import TelemetryConnectionsWorkspace from "./TelemetryConnectionsWorkspace";

const h = React.createElement;
const CONNECTION_ID = "11111111-1111-4111-8111-111111111111";
const SIGNAL_ID = "22222222-2222-4222-8222-222222222222";
const CONCEPT_ID = "33333333-3333-4333-8333-333333333333";

function response(payload, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: vi.fn().mockResolvedValue(payload) };
}

function connection(overrides = {}) {
  return {
    connection_id: CONNECTION_ID,
    resource_scope_id: "scope-facility-a",
    facility_id: "facility-a",
    name: "Central plant API",
    connector_type: "https_telemetry",
    lifecycle_status: "validated",
    enabled: false,
    configuration: { base_url: "https://telemetry.example" },
    timezone: "UTC",
    polling_interval_seconds: 300,
    credentials_configured: true,
    health: {
      aggregate_status: "degraded",
      credentials_state: "valid",
      endpoint_state: "reachable",
      telemetry_state: "arriving",
      mapping_state: "incomplete",
      freshness_state: "current",
      quality_state: "acceptable",
      mapped_signal_count: 0,
      stale_signal_count: 0,
    },
    ...overrides,
  };
}

function signal(overrides = {}) {
  return {
    signal_id: SIGNAL_ID,
    connection_id: CONNECTION_ID,
    external_tag_id: "BAS.CHW.P1.KW",
    external_tag_name: "P1 Power",
    display_label: "Primary pump power",
    source_unit: "kW",
    sample_cadence_seconds: 300,
    enabled: false,
    mapping_status: "unmapped",
    quality_state: "mapping_required",
    ...overrides,
  };
}

function basePayload(path) {
  if (path === "/api/data-connections") return response({ connections: [] });
  if (path === "/api/data-connections/providers") return response({ providers: [{ connector_type: "https_telemetry", display_name: "HTTPS telemetry API", description: "Read telemetry from a public HTTPS API.", capabilities: ["discover", "read_incremental"], available: true, retrieval_only: true, configuration_mode: "safe_https_metadata" }, { connector_type: "historian_template", display_name: "Managed historian profile", description: "Read telemetry through an approved historian profile.", capabilities: ["discover", "read_incremental", "read_backfill"], available: false, retrieval_only: true, configuration_mode: "server_owned_template" }] });
  if (path === "/api/data-connections/signal-concepts") return response({ concepts: [{ canonical_signal_id: CONCEPT_ID, canonical_name: "power", display_name: "Power", physical_dimension: "power", canonical_unit: "kW", taxonomy_version: 1 }] });
  if (path === "/api/facility/context") return response({ site_id: "facility-a", site_name: "Central Plant", timezone: "UTC", systems: [{ system_id: "chw-loop", name: "Chilled water loop", system_type: "chilled_water", equipment_ids: ["pump-1"] }], equipment: [{ equipment_id: "pump-1", name: "Primary pump", system_id: "chw-loop", equipment_type: "pump" }], signal_mappings: [] });
  return null;
}

afterEach(() => cleanup());

describe("TelemetryConnectionsWorkspace", () => {
  it("uses system-first onboarding and does not expose historical upload to a normal customer", async () => {
    const apiFetch = vi.fn(async (path) => basePayload(path) ?? response({}, 404));
    render(h(TelemetryConnectionsWorkspace, { apiFetch, currentUser: { role: "admin" }, currentWorkspace: { display_name: "Central Plant" }, datasetScopeKey: "facility-a" }));

    expect(await screen.findByRole("heading", { name: "Connect a physical system" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "No telemetry source connected" })).toBeTruthy();
    expect(screen.queryByText(/upload historical/i)).toBeNull();
    expect(screen.queryByText(/import dataset/i)).toBeNull();
    expect(screen.getByText(/signals within a defined system behave together/i)).toBeTruthy();
  });

  it("uses the production provider catalog and explains unavailable historian prerequisites", async () => {
    const apiFetch = vi.fn(async (path) => basePayload(path) ?? response({}, 404));
    render(h(TelemetryConnectionsWorkspace, { apiFetch, currentUser: { role: "admin" }, datasetScopeKey: "facility-a" }));
    await screen.findByRole("heading", { name: "No telemetry source connected" });
    fireEvent.click(screen.getAllByRole("button", { name: "Add data source" })[0]);

    expect(screen.getByRole("radio", { name: /HTTPS telemetry API/i }).disabled).toBe(false);
    expect(screen.getByRole("radio", { name: /Managed historian profile/i }).disabled).toBe(true);
    expect(screen.getByText(/Unavailable until an administrator configures an approved server-owned template and network profile/i)).toBeTruthy();
    expect(apiFetch).toHaveBeenCalledWith("/api/data-connections/providers", expect.objectContaining({ cache: "no-store" }));
    expect(apiFetch.mock.calls.some(([path]) => path === "/api/connectors/types")).toBe(false);
  });

  it("completes create, one-way credential, validate, discover, map, and enable", async () => {
    let created = null;
    let discovered = false;
    let mapped = false;
    const apiFetch = vi.fn(async (path, options = {}) => {
      const initial = basePayload(path);
      if (initial && !(path === "/api/data-connections" && options.method === "POST")) return initial;
      if (path === "/api/data-connections" && options.method === "POST") {
        created = connection({ lifecycle_status: "draft", credentials_configured: false });
        return response({ connection: created, message: "created" }, 201);
      }
      if (path.endsWith("/credentials")) return response({ credentials_configured: true, credential_version: "v1" });
      if (path.endsWith("/validate")) return response({ connection: connection(), valid: true, reachable: true, authenticated: true, observations_sampled: 3, code: "telemetry_connection_valid" });
      if (path.endsWith("/discover")) { discovered = true; return response({ connection_id: CONNECTION_ID, discovered_count: 1, registered_count: 1, has_more: false, checkpoint: null }); }
      if (path.includes("/signals?") && discovered) return response({ signals: [mapped ? signal({ mapping_status: "mapped", enabled: true, system_id: "chw-loop", asset_id: "pump-1", canonical_signal_id: CONCEPT_ID, canonical_signal_name: "power", canonical_unit: "kW" }) : signal()] });
      if (path.includes("/signals?")) return response({ signals: [] });
      if (path.endsWith(`/signals/${SIGNAL_ID}/mapping`)) { mapped = true; return response({ signal: signal({ mapping_status: "mapped", enabled: true, system_id: "chw-loop", asset_id: "pump-1", canonical_signal_id: CONCEPT_ID, canonical_signal_name: "power", canonical_unit: "kW" }), message: "mapped" }); }
      if (path.endsWith("/enable")) return response({ connection: connection({ lifecycle_status: "enabled", enabled: true, health: { ...connection().health, mapping_state: "complete", mapped_signal_count: 1 } }), message: "enabled" });
      if (path.includes("/runs?")) return response({ runs: [] });
      if (path.includes("/errors?")) return response({ errors: [] });
      return response({}, 404);
    });

    render(h(TelemetryConnectionsWorkspace, { apiFetch, currentUser: { role: "admin" }, currentWorkspace: { display_name: "Central Plant" }, datasetScopeKey: "facility-a" }));
    await screen.findByRole("heading", { name: "No telemetry source connected" });
    fireEvent.click(screen.getAllByRole("button", { name: "Add data source" })[0]);
    fireEvent.change(screen.getByLabelText("Connection name"), { target: { value: "Central plant API" } });
    fireEvent.change(screen.getByLabelText("HTTPS origin"), { target: { value: "https://telemetry.example" } });
    fireEvent.click(screen.getByRole("button", { name: "Save connection metadata" }));

    expect(await screen.findByRole("heading", { name: "Attach credential securely" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Bearer token"), { target: { value: "opaque-canary-secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Store credential securely" }));
    expect(await screen.findByRole("button", { name: "Validate" })).toBeTruthy();
    expect(screen.queryByDisplayValue("opaque-canary-secret")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByText(/endpoint reachable, authentication valid/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Discover" }));
    expect(await screen.findByText("Primary pump power")).toBeTruthy();
    expect(screen.getByText("Unmapped · not analyzed")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Map signal" }));
    fireEvent.change(screen.getByLabelText("Defined system"), { target: { value: "chw-loop" } });
    fireEvent.change(screen.getByLabelText("Asset / equipment"), { target: { value: "pump-1" } });
    fireEvent.change(screen.getByLabelText("Canonical signal concept"), { target: { value: CONCEPT_ID } });
    fireEvent.click(screen.getByRole("button", { name: "Approve mapping" }));
    expect(await screen.findByText(/Signal accepted into the defined system/i)).toBeTruthy();

    const setup = screen.getByRole("heading", { name: "Enable continued analysis" }).closest("article");
    fireEvent.click(within(setup).getByRole("button", { name: "Enable analysis" }));
    expect(await screen.findByText("Continued read-only ingestion and system-level analysis enabled.")).toBeTruthy();
    expect(created.resource_scope_id).toBe("scope-facility-a");

    const credentialRequest = apiFetch.mock.calls.find(([path]) => path.endsWith("/credentials"));
    expect(JSON.parse(credentialRequest[1].body)).toEqual({ values: { bearer_token: "opaque-canary-secret" } });
  });

  it("renders health facets and sanitized ingestion errors without conflating authentication with connection health", async () => {
    const apiFetch = vi.fn(async (path) => {
      if (path === "/api/data-connections") return response({ connections: [connection()] });
      const initial = basePayload(path);
      if (initial) return initial;
      if (path.includes("/signals?")) return response({ signals: [signal()] });
      if (path.includes("/runs?")) return response({ runs: [{ run_id: "44444444-4444-4444-8444-444444444444", connection_id: CONNECTION_ID, mode: "incremental", status: "partial", started_at: "2026-08-26T00:00:00Z", observations_accepted: 20, observations_rejected: 1, observations_duplicate: 2 }] });
      if (path.includes("/errors?")) return response({ errors: [{ error_id: "55555555-5555-4555-8555-555555555555", run_id: "44444444-4444-4444-8444-444444444444", external_tag_id: "BAS.CHW.P1.KW", quality_state: "invalid_unit", reason_code: "telemetry_unit_incompatible", disposition: "quarantined", occurrence_count: 1, first_seen_at: "2026-08-26T00:00:00Z", last_seen_at: "2026-08-26T00:01:00Z" }] });
      return response({}, 404);
    });
    render(h(TelemetryConnectionsWorkspace, { apiFetch, currentUser: { role: "operator" }, datasetScopeKey: "facility-a" }));

    expect(await screen.findByRole("heading", { name: "Central plant API" })).toBeTruthy();
    for (const label of ["Credentials valid", "Endpoint reachable", "Telemetry arriving", "Mappings complete", "Data current", "Data quality acceptable"]) expect(screen.getByText(label)).toBeTruthy();
    expect(await screen.findByText("Telemetry unit incompatible")).toBeTruthy();
    expect(screen.queryByText(/traceback|secret|authorization:/i)).toBeNull();
    expect(screen.queryByRole("button", { name: "Add data source" })).toBeNull();
  });

  it("fails closed when connections from more than one server scope are returned", async () => {
    const apiFetch = vi.fn(async (path) => {
      if (path === "/api/data-connections") return response({ connections: [connection(), connection({ connection_id: "66666666-6666-4666-8666-666666666666", resource_scope_id: "scope-other" })] });
      return basePayload(path) ?? response({});
    });
    render(h(TelemetryConnectionsWorkspace, { apiFetch, currentUser: { role: "admin" }, datasetScopeKey: "facility-a" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Telemetry authority could not be established for this facility.");
    expect(screen.queryByText("Central plant API")).toBeNull();
  });

  it("retrieves an exact scoped canonical result without using the historical latest-result path", async () => {
    const runId = "44444444-4444-4444-8444-444444444444";
    const resultId = "77777777-7777-4777-8777-777777777777";
    const onOpenAnalysisResult = vi.fn();
    const apiFetch = vi.fn(async (path) => {
      if (path === "/api/data-connections") return response({ connections: [connection()] });
      const initial = basePayload(path);
      if (initial) return initial;
      if (path.includes("/signals?")) return response({ signals: [signal()] });
      if (path.includes("/runs?")) return response({ runs: [{ run_id: runId, connection_id: CONNECTION_ID, mode: "incremental", status: "succeeded", observations_accepted: 20, observations_rejected: 0, observations_duplicate: 0 }] });
      if (path.includes("/errors?")) return response({ errors: [] });
      if (path === `/api/data-connections/${CONNECTION_ID}/runs/${runId}/analysis-results`) return response({ results: [{ result_id: resultId, system_id: "chw-loop", asset_id: "pump-1" }] });
      if (path === `/api/data-connections/${CONNECTION_ID}/runs/${runId}/systems/chw-loop/analysis-results/${resultId}?asset_id=pump-1`) return response({ result_id: resultId, analysis_window_id: "88888888-8888-4888-8888-888888888888", connection_id: CONNECTION_ID, source_run_id: runId, system_id: "chw-loop", asset_id: "pump-1", payload_digest: "a".repeat(64), lineage_verified: true, product_result: { result_id: resultId, analysis_result: { systems: [{ id: "chw-loop", name: "Chilled water loop" }], conditions: [], insights: [] } } });
      return response({}, 404);
    });

    render(h(TelemetryConnectionsWorkspace, { apiFetch, currentUser: { role: "viewer" }, datasetScopeKey: "facility-a", onOpenAnalysisResult }));
    fireEvent.click(await screen.findByRole("button", { name: "Review results" }));

    await waitFor(() => expect(onOpenAnalysisResult).toHaveBeenCalledWith(expect.objectContaining({ result_id: resultId })));
    expect(apiFetch).toHaveBeenCalledWith(`/api/data-connections/${CONNECTION_ID}/runs/${runId}/analysis-results`, expect.objectContaining({ cache: "no-store" }));
    expect(apiFetch).toHaveBeenCalledWith(`/api/data-connections/${CONNECTION_ID}/runs/${runId}/systems/chw-loop/analysis-results/${resultId}?asset_id=pump-1`, expect.objectContaining({ cache: "no-store" }));
    expect(apiFetch.mock.calls.some(([path]) => String(path).includes("/api/data/latest"))).toBe(false);
  });
});
