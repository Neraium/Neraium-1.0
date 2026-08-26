import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures";

const CONNECTION_ID = "11111111-1111-4111-8111-111111111111";
const SIGNAL_ID = "22222222-2222-4222-8222-222222222222";
const CONCEPT_ID = "33333333-3333-4333-8333-333333333333";

function connection(overrides = {}) {
  return {
    connection_id: CONNECTION_ID,
    resource_scope_id: "scope-default",
    facility_id: "default",
    name: "Central plant API",
    connector_type: "https_telemetry",
    lifecycle_status: "validated",
    enabled: false,
    configuration: { base_url: "https://telemetry.customer.example" },
    timezone: "UTC",
    polling_interval_seconds: 300,
    credentials_configured: true,
    last_telemetry_at: "2026-08-26T10:00:00Z",
    last_success_at: "2026-08-26T10:00:00Z",
    health: { aggregate_status: "degraded", credentials_state: "valid", endpoint_state: "reachable", telemetry_state: "arriving", mapping_state: "incomplete", freshness_state: "current", quality_state: "acceptable", mapped_signal_count: 0, stale_signal_count: 0 },
    ...overrides,
  };
}

async function mockTelemetryApi(page) {
  let savedConnection = null;
  let discovered = false;
  let mapped = false;
  await page.route("**/api/facility/context", (route) => route.fulfill({ json: { site_id: "default", site_name: "Synthetic facility", timezone: "UTC", systems: [{ system_id: "chw-loop", name: "Chilled water loop", system_type: "chilled_water", equipment_ids: ["pump-1"] }], equipment: [{ equipment_id: "pump-1", name: "Primary pump", system_id: "chw-loop", equipment_type: "pump" }], signal_mappings: [] } }));
  await page.route("**/api/data-connections**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    if (path === "/api/data-connections/providers") return route.fulfill({ json: { providers: [{ connector_type: "https_telemetry", display_name: "HTTPS telemetry API", description: "Read telemetry from a public HTTPS API.", capabilities: ["discover", "read_incremental"], available: true, retrieval_only: true, configuration_mode: "safe_https_metadata" }, { connector_type: "historian_template", display_name: "Managed historian profile", description: "Read telemetry through an approved historian profile.", capabilities: ["discover", "read_incremental", "read_backfill"], available: false, retrieval_only: true, configuration_mode: "server_owned_template" }] } });
    if (path === "/api/data-connections/signal-concepts") return route.fulfill({ json: { concepts: [{ canonical_signal_id: CONCEPT_ID, canonical_name: "power", display_name: "Power", physical_dimension: "power", canonical_unit: "kW", taxonomy_version: 1 }] } });
    if (path === "/api/data-connections" && method === "GET") return route.fulfill({ json: { connections: savedConnection ? [savedConnection] : [] } });
    if (path === "/api/data-connections" && method === "POST") { savedConnection = connection({ lifecycle_status: "draft", credentials_configured: false, last_telemetry_at: null, last_success_at: null }); return route.fulfill({ status: 201, json: { connection: savedConnection, message: "created" } }); }
    if (path.endsWith("/credentials")) { savedConnection = { ...savedConnection, credentials_configured: true }; return route.fulfill({ json: { credentials_configured: true, credential_version: "v1" } }); }
    if (path.endsWith("/validate")) { savedConnection = connection(); return route.fulfill({ json: { connection: savedConnection, valid: true, reachable: true, authenticated: true, observations_sampled: 3, code: "telemetry_connection_valid" } }); }
    if (path.endsWith("/discover")) { discovered = true; return route.fulfill({ json: { connection_id: CONNECTION_ID, discovered_count: 1, registered_count: 1, has_more: false, checkpoint: null } }); }
    if (path.includes(`/signals/${SIGNAL_ID}/mapping`)) { mapped = true; return route.fulfill({ json: { signal: { signal_id: SIGNAL_ID, connection_id: CONNECTION_ID, external_tag_id: "BAS.CHW.P1.KW", external_tag_name: "P1 Power", display_label: "Primary pump power", source_unit: "kW", enabled: true, mapping_status: "mapped", quality_state: "good", system_id: "chw-loop", asset_id: "pump-1", canonical_signal_id: CONCEPT_ID, canonical_signal_name: "power", canonical_unit: "kW" }, message: "mapped" } }); }
    if (path.endsWith("/signals") && method === "GET") return route.fulfill({ json: { signals: discovered ? [{ signal_id: SIGNAL_ID, connection_id: CONNECTION_ID, external_tag_id: "BAS.CHW.P1.KW", external_tag_name: "P1 Power", display_label: "Primary pump power", source_unit: "kW", sample_cadence_seconds: 300, enabled: mapped, mapping_status: mapped ? "mapped" : "unmapped", quality_state: mapped ? "good" : "mapping_required", ...(mapped ? { system_id: "chw-loop", asset_id: "pump-1", canonical_signal_id: CONCEPT_ID, canonical_signal_name: "power", canonical_unit: "kW" } : {}) }] : [] } });
    if (path.endsWith("/runs")) return route.fulfill({ json: { runs: [] } });
    if (path.endsWith("/errors")) return route.fulfill({ json: { errors: [] } });
    if (path.endsWith("/enable")) { savedConnection = connection({ enabled: true, lifecycle_status: "enabled", health: { ...connection().health, aggregate_status: "healthy", mapping_state: "complete", mapped_signal_count: 1 } }); return route.fulfill({ json: { connection: savedConnection, message: "enabled" } }); }
    return route.fulfill({ status: 404, json: { detail: { code: "not_found", message: "Unavailable" } } });
  });
}

async function completeFlow(page, screenshotName) {
  await mockTelemetryApi(page);
  await page.goto("/workspace/data-sources");
  await expect(page.getByRole("heading", { name: "Connect a physical system" })).toBeVisible();
  await expect(page.getByText(/Upload historical data/i)).toHaveCount(0);
  await page.getByRole("button", { name: "Add data source" }).first().click();
  await page.getByLabel("Connection name").fill("Central plant API");
  await page.getByRole("textbox", { name: "HTTPS origin", exact: true }).fill("https://telemetry.customer.example");
  await page.getByRole("button", { name: "Save connection metadata" }).click();
  await page.getByLabel("Bearer token").fill("browser-canary-secret");
  await page.getByRole("button", { name: "Store credential securely" }).click();
  await expect(page.locator('input[value="browser-canary-secret"]')).toHaveCount(0);
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByText(/endpoint reachable, authentication valid/i)).toBeVisible();
  await page.getByRole("button", { name: "Discover" }).click();
  await page.getByRole("button", { name: "Map signal" }).click();
  await page.getByLabel("Defined system").selectOption("chw-loop");
  await page.getByLabel("Asset / equipment").selectOption("pump-1");
  await page.getByLabel("Canonical signal concept").selectOption(CONCEPT_ID);
  await page.getByRole("button", { name: "Approve mapping" }).click();
  await page.getByRole("button", { name: "Enable analysis" }).click();
  await expect(page.getByText("Continued read-only ingestion and system-level analysis enabled.")).toBeVisible();
  await expect(page.getByText("Credentials valid")).toBeVisible();
  await expect(page.getByText("Data quality acceptable")).toBeVisible();
  const accessibility = await new AxeBuilder({ page }).include("[data-testid='telemetry-connections-workspace']").analyze();
  expect(accessibility.violations).toEqual([]);
  await page.screenshot({ path: `../.planning/screenshots/generic-telemetry-ingestion/${screenshotName}`, fullPage: !screenshotName.includes("390") });
}

test("production Data Connections flow completes at desktop", async ({ page }) => {
  await completeFlow(page, "data-connections-desktop.png");
});

test("production Data Connections flow completes at 390px", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await completeFlow(page, "data-connections-390.png");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
});
