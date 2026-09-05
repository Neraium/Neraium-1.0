import fs from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures";

const CONNECTION_ID = "11111111-1111-4111-8111-111111111111";
const SIGNAL_ID = "22222222-2222-4222-8222-222222222222";
const CONCEPT_ID = "33333333-3333-4333-8333-333333333333";
const RUN_ID = "44444444-4444-4444-8444-444444444444";
const RESULT_ID = "77777777-7777-4777-8777-777777777777";
const WINDOW_ID = "88888888-8888-4888-8888-888888888888";
const FINDING_ID = "connector-finding-1";
const PAYLOAD_DIGEST = "a".repeat(64);
const LINEAGE_DIGEST = "d".repeat(64);
const OBSERVATION_ID = "99999999-9999-4999-8999-999999999999";

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

async function mockTelemetryApi(page, { existingConnection = null, runs = [], canonicalResult = null } = {}) {
  let savedConnection = existingConnection;
  let discovered = Boolean(existingConnection);
  let mapped = Boolean(existingConnection);
  const requests = [];
  await page.route("**/api/facility/context", (route) => route.fulfill({ json: { site_id: "default", site_name: "Synthetic facility", timezone: "UTC", systems: [{ system_id: "chw-loop", name: "Chilled water loop", system_type: "chilled_water", equipment_ids: ["pump-1"] }], equipment: [{ equipment_id: "pump-1", name: "Primary pump", system_id: "chw-loop", equipment_type: "pump" }], signal_mappings: [] } }));
  await page.route("**/api/data-connections**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    requests.push({ method, path });
    if (path === "/api/data-connections/providers") return route.fulfill({ json: { providers: [{ connector_type: "https_telemetry", display_name: "HTTPS telemetry API", description: "Read telemetry from a public HTTPS API.", capabilities: ["discover", "read_incremental"], available: true, retrieval_only: true, configuration_mode: "safe_https_metadata" }, { connector_type: "historian_template", display_name: "Managed historian profile", description: "Read telemetry through an approved historian profile.", capabilities: ["discover", "read_incremental", "read_backfill"], available: false, retrieval_only: true, configuration_mode: "server_owned_template" }] } });
    if (path === "/api/data-connections/signal-concepts") return route.fulfill({ json: { concepts: [{ canonical_signal_id: CONCEPT_ID, canonical_name: "power", display_name: "Power", physical_dimension: "power", canonical_unit: "kW", taxonomy_version: 1 }] } });
    if (path === "/api/data-connections" && method === "GET") return route.fulfill({ json: { connections: savedConnection ? [savedConnection] : [] } });
    if (path === "/api/data-connections" && method === "POST") { savedConnection = connection({ lifecycle_status: "draft", credentials_configured: false, last_telemetry_at: null, last_success_at: null }); return route.fulfill({ status: 201, json: { connection: savedConnection, message: "created" } }); }
    if (path.endsWith("/credentials")) { savedConnection = { ...savedConnection, credentials_configured: true }; return route.fulfill({ json: { credentials_configured: true, credential_version: "v1" } }); }
    if (path.endsWith("/validate")) { savedConnection = connection(); return route.fulfill({ json: { connection: savedConnection, valid: true, reachable: true, authenticated: true, observations_sampled: 3, code: "telemetry_connection_valid" } }); }
    if (path.endsWith("/discover")) { discovered = true; return route.fulfill({ json: { connection_id: CONNECTION_ID, discovered_count: 1, registered_count: 1, has_more: false, checkpoint: null } }); }
    if (path.includes(`/signals/${SIGNAL_ID}/mapping`)) { mapped = true; return route.fulfill({ json: { signal: { signal_id: SIGNAL_ID, connection_id: CONNECTION_ID, external_tag_id: "BAS.CHW.P1.KW", external_tag_name: "P1 Power", display_label: "Primary pump power", source_unit: "kW", enabled: true, mapping_status: "mapped", quality_state: "good", system_id: "chw-loop", asset_id: "pump-1", canonical_signal_id: CONCEPT_ID, canonical_signal_name: "power", canonical_unit: "kW" }, message: "mapped" } }); }
    if (path.endsWith("/signals") && method === "GET") return route.fulfill({ json: { signals: discovered ? [{ signal_id: SIGNAL_ID, connection_id: CONNECTION_ID, external_tag_id: "BAS.CHW.P1.KW", external_tag_name: "P1 Power", display_label: "Primary pump power", source_unit: "kW", sample_cadence_seconds: 300, enabled: mapped, mapping_status: mapped ? "mapped" : "unmapped", quality_state: mapped ? "good" : "mapping_required", ...(mapped ? { system_id: "chw-loop", asset_id: "pump-1", canonical_signal_id: CONCEPT_ID, canonical_signal_name: "power", canonical_unit: "kW" } : {}) }] : [] } });
    if (canonicalResult && path === `/api/data-connections/${CONNECTION_ID}/runs/${RUN_ID}/analysis-results`) return route.fulfill({ json: { results: [{ result_id: RESULT_ID, analysis_window_id: WINDOW_ID, source_run_id: RUN_ID, connection_id: CONNECTION_ID, system_id: "chw-loop", asset_id: "pump-1", payload_digest: PAYLOAD_DIGEST }] } });
    if (canonicalResult && path === `/api/data-connections/${CONNECTION_ID}/runs/${RUN_ID}/systems/chw-loop/analysis-results/${RESULT_ID}/lineage`) return route.fulfill({ json: { result_id: RESULT_ID, analysis_window_id: WINDOW_ID, observation_count: 1, observation_lineage_digest: LINEAGE_DIGEST, lineage_verified: true, records: [{ observation_id: OBSERVATION_ID, connection_id: CONNECTION_ID, system_id: "chw-loop", asset_id: "pump-1", observed_at: "2026-08-26T10:00:00Z", source_tag_id: "BAS.CHW.P1.KW", canonical_signal_id: CONCEPT_ID }], next_cursor: null } });
    if (canonicalResult && path === `/api/data-connections/${CONNECTION_ID}/runs/${RUN_ID}/systems/chw-loop/analysis-results/${RESULT_ID}`) return route.fulfill({ json: canonicalResult });
    if (path.endsWith("/runs")) return route.fulfill({ json: { runs } });
    if (path.endsWith("/errors")) return route.fulfill({ json: { errors: [] } });
    if (path.endsWith("/enable")) { savedConnection = connection({ enabled: true, lifecycle_status: "enabled", health: { ...connection().health, aggregate_status: "healthy", mapping_state: "complete", mapped_signal_count: 1 } }); return route.fulfill({ json: { connection: savedConnection, message: "enabled" } }); }
    return route.fulfill({ status: 404, json: { detail: { code: "not_found", message: "Unavailable" } } });
  });
  return requests;
}

function canonicalResultDetail() {
  const relationship = {
    id: "connector-relationship-1",
    columns: ["BAS.CHW.P1.KW", "BAS.CHW.P1.FLOW"],
    change_type: "changed",
    baseline_strength: 0.81,
    current_strength: 0.42,
    correlation_delta: -0.39,
  };
  const analysisResult = {
    schema_version: "analysis-result-v1",
    status: "complete",
    analysis_id: "connector-analysis-1",
    generated_at: "2026-08-26T10:05:00Z",
    data_quality: { status: "sufficient", coverage_percent: 100, warnings: [] },
    systems: [{ id: "chw-loop", name: "Chilled water loop" }],
    relationships: [relationship],
    insights: [{
      id: FINDING_ID,
      title: "Pump response changed",
      system: "Chilled water loop",
      system_id: "chw-loop",
      asset: "Primary pump",
      asset_id: "pump-1",
      confidence: "high",
      what_changed: "Pump power response weakened during comparable operation.",
      why_it_matters: "The mapped pump response differs from the learned operating pattern.",
      variables: ["BAS.CHW.P1.KW", "BAS.CHW.P1.FLOW"],
      supporting_evidence: ["The relationship moved outside its learned range."],
      contributing_relationships: [relationship],
      classification: { type: "unexplained_systemic_change", confidence: "high", reasons: ["The relationship change persisted."] },
      data_confidence: { rating: "high", summary: "Telemetry passed recorded quality checks." },
      operating_mode: { match: "strong", confidence: "high", baseline_mode_label: "Mid-load", recent_mode_label: "Mid-load" },
      persistence: { persistent: true, duration: "3 windows", summary: "The change persisted across comparable windows." },
      finding_confidence_v1: { change_detection: { level: "high" }, relationship_comparison: { metric: "pearson_correlation", baseline_value: 0.81, current_value: 0.42, signed_change: -0.39, absolute_change: 0.39, direction: "decreased" } },
      investigation_guidance: [{ rank: 1, check: "Verify the mapped pump signals.", reason: "Source validation bounds interpretation.", category: "data_quality" }],
      certainty_limit: "The evidence does not establish a cause.",
      evidence_refs: ["connector-evidence-1"],
    }],
    evidence_index: { "connector-evidence-1": { id: "connector-evidence-1", statement: "The exact relationship comparison supports this finding." } },
    telemetry_signals: [{ signal_id: SIGNAL_ID, canonical_signal_id: CONCEPT_ID, display_name: "Primary pump power" }],
    analysis_metadata: { contract_version: "analysis-result-v1" },
  };
  const identity = {
    result_id: RESULT_ID,
    analysis_id: "connector-analysis-1",
    analysis_window_id: WINDOW_ID,
    source_ingestion_run_id: RUN_ID,
    connection_id: CONNECTION_ID,
    tenant_scope_id: "tenant-e2e",
    workspace_id: "default",
    resource_scope_id: "scope-default",
    facility_id: "default",
    system_id: "chw-loop",
    asset_id: "pump-1",
    window_start: "2026-08-26T09:00:00Z",
    window_end: "2026-08-26T10:00:00Z",
    observation_count: 1,
    observation_lineage_digest: LINEAGE_DIGEST,
    payload_digest: PAYLOAD_DIGEST,
    engine_name: "SII",
    engine_version: "4.2",
    artifact_schema_version: "telemetry-canonical-result-artifact.v1",
    execution_contract_version: "analysis-window-execution.v1",
    analysis_schema_version: "analysis-result-v1",
    analysis_contract_version: "analysis-result-v1",
  };
  return {
    result_id: RESULT_ID,
    analysis_window_id: WINDOW_ID,
    connection_id: CONNECTION_ID,
    source_run_id: RUN_ID,
    facility_id: "default",
    system_id: "chw-loop",
    asset_id: "pump-1",
    window_start: identity.window_start,
    window_end: identity.window_end,
    artifact_schema_version: identity.artifact_schema_version,
    execution_contract_version: identity.execution_contract_version,
    analysis_schema_version: identity.analysis_schema_version,
    analysis_contract_version: identity.analysis_contract_version,
    payload_digest: PAYLOAD_DIGEST,
    payload_uncompressed_bytes: 8192,
    payload_stored_bytes: 2048,
    serialization_ms: 1.25,
    projection_bytes: 6144,
    retrieval_ms: 2.5,
    lineage_verified: true,
    product_result: {
      identity,
      source_type: "telemetry_connector",
      source_kind: "telemetry_connection",
      status: "completed",
      availability: "available",
      product_boundary: { mode: "read_only", control_actions: [] },
      lineage: { analysis_window_id: WINDOW_ID, observation_count: 1, digest: LINEAGE_DIGEST, verified: true, detail_source: "analysis_window_observations" },
      analysis_result: analysisResult,
      sii_result: {
        engine: { name: "SII", version: "4.2" },
        relationship_analysis: { status: "complete", relationships: [relationship] },
        persistence_analysis: { status: "persistent" },
        operating_modes: { status: "comparable" },
        data_conditions: { status: "sufficient" },
        provenance: { analysis_run_id: RUN_ID },
      },
      canonical_result: {
        identity,
        reference_metadata: { baseline_snapshot_id: "baseline-snapshot-e2e" },
        finding_ids: { ids: [FINDING_ID], count: 1, truncated: false },
        evidence_ids: { ids: ["connector-evidence-1"], count: 1, truncated: false },
        evidence_audit: { identity: { result_id: RESULT_ID }, finding_record_count: 1 },
      },
      projection: {
        contract_version: "telemetry-canonical-result-product.v1",
        canonical_result_id: RESULT_ID,
        canonical_payload_digest: PAYLOAD_DIGEST,
        shared: { source_path: "analysis_result", bytes: 4096, truncated: false, omitted_values: 0 },
        technical_channels: { relationship_analysis: { source_path: "sii_result.relationship_analysis", bytes: 512, truncated: false, omitted_values: 0, transported: true } },
        technical_channels_bytes: 512,
        evidence_audit: { source_path: "analysis_result.conditions|analysis_result.insights", bytes: 1024, truncated: false, omitted_values: 0 },
      },
      result_id: RESULT_ID,
      analysis_id: identity.analysis_id,
      analysis_window_id: WINDOW_ID,
      connection_id: CONNECTION_ID,
      source_run_id: RUN_ID,
      analysis_run_id: RUN_ID,
      run_id: RUN_ID,
      facility_id: "default",
      system_id: "chw-loop",
      asset_id: "pump-1",
      window_start: identity.window_start,
      window_end: identity.window_end,
      data_quality: analysisResult.data_quality,
      engine: { name: "SII", version: "4.2" },
      engine_name: "SII",
      engine_version: "4.2",
      schema_version: "analysis-result-v1",
      payload_digest: PAYLOAD_DIGEST,
      result_hash: PAYLOAD_DIGEST,
      lineage_verified: true,
    },
  };
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

test("persisted connector result routes through every evidence depth without rerunning analysis", async ({ page }) => {
  const analysisMutations = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (request.method() !== "GET" && (/\/api\/(?:analysis|sii)(?:\/|$)/.test(path) || /\/api\/data-connections\/.*\/(?:retry|backfills)$/.test(path))) {
      analysisMutations.push(`${request.method()} ${path}`);
    }
  });
  const requests = await mockTelemetryApi(page, {
    existingConnection: connection({ enabled: true, lifecycle_status: "enabled", health: { ...connection().health, aggregate_status: "healthy", mapping_state: "complete", mapped_signal_count: 1 } }),
    runs: [{ run_id: RUN_ID, connection_id: CONNECTION_ID, mode: "incremental", status: "succeeded", started_at: "2026-08-26T09:00:00Z", completed_at: "2026-08-26T10:05:00Z", observations_accepted: 1, observations_rejected: 0, observations_duplicate: 0 }],
    canonicalResult: canonicalResultDetail(),
  });

  await page.goto("/workspace/data-sources");
  await page.getByRole("button", { name: "Review results" }).click();

  await expect(page).toHaveURL(/\/sites\/current$/);
  await expect(page.getByRole("heading", { name: "Analysis complete" })).toBeVisible();
  const resultCard = page.getByTestId("compact-finding-card");
  await expect(resultCard).toHaveAttribute("data-finding-key", FINDING_ID);
  await expect(resultCard).toContainText("Pump power response decreased during comparable operation.");
  await expect(resultCard).not.toContainText(PAYLOAD_DIGEST);

  await resultCard.getByRole("button", { name: "Review finding" }).click();
  await expect(page).toHaveURL(new RegExp(`/findings/${FINDING_ID}$`));
  await expect(page.getByTestId("finding-review")).toContainText("Pump power response decreased during comparable operation.");

  await page.getByRole("button", { name: "Open investigation" }).click();
  await expect(page).toHaveURL(new RegExp(`/investigations/${FINDING_ID}$`));
  await expect(page.getByTestId("investigation-workspace")).toContainText(RESULT_ID);
  await expect(page.getByTestId("investigation-workspace")).toContainText("telemetry-canonical-result-product.v1");

  await page.getByRole("button", { name: "Open evidence record" }).click();
  await expect(page).toHaveURL(new RegExp(`/evidence/${FINDING_ID}$`));
  const evidenceRecord = page.getByTestId("evidence-record");
  await expect(evidenceRecord).toContainText(FINDING_ID);
  await expect(evidenceRecord).toContainText(RESULT_ID);
  await expect(evidenceRecord).toContainText(PAYLOAD_DIGEST);
  await expect(evidenceRecord).toContainText(LINEAGE_DIGEST);
  await expect(evidenceRecord).toContainText("1 observations verified against");
  await expect(evidenceRecord).toContainText(OBSERVATION_ID);

  const resultReads = requests.filter(({ method, path }) => method === "GET" && path.includes("/analysis-results"));
  expect(resultReads).toEqual([
    { method: "GET", path: `/api/data-connections/${CONNECTION_ID}/runs/${RUN_ID}/analysis-results` },
    { method: "GET", path: `/api/data-connections/${CONNECTION_ID}/runs/${RUN_ID}/systems/chw-loop/analysis-results/${RESULT_ID}` },
    { method: "GET", path: `/api/data-connections/${CONNECTION_ID}/runs/${RUN_ID}/systems/chw-loop/analysis-results/${RESULT_ID}/lineage` },
  ]);
  expect(analysisMutations).toEqual([]);
});


const measuredWaterConsequence = JSON.parse(fs.readFileSync(new URL("../fixtures/measurable-consequence.json", import.meta.url), "utf8"));

async function openMeasuredFinding(page, consequence) {
  const detail = canonicalResultDetail();
  detail.product_result.analysis_result.insights[0].measurable_consequence = { ...consequence, finding_id: FINDING_ID };
  await mockTelemetryApi(page, {
    existingConnection: connection({ enabled: true, lifecycle_status: "enabled" }),
    runs: [{ run_id: RUN_ID, connection_id: CONNECTION_ID, mode: "incremental", status: "succeeded", started_at: "2026-08-26T09:00:00Z", completed_at: "2026-08-26T10:05:00Z", observations_accepted: 1 }],
    canonicalResult: detail,
  });
  await page.goto("/workspace/data-sources");
  await page.getByRole("button", { name: "Review results" }).click();
  await page.getByTestId("compact-finding-card").getByRole("button", { name: "Review finding" }).click();
  await expect(page.getByRole("region", { name: "Measurable consequence" })).toBeVisible();
}

for (const width of [1440, 390]) {
  test(`measurable consequence survives canonical Findings and Evidence navigation at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await openMeasuredFinding(page, measuredWaterConsequence);
    const section = page.getByRole("region", { name: "Measurable consequence" });
    await expect(section.getByText("Water use above expected")).toBeVisible();
    await expect(section.getByText("12,840 gal")).toBeVisible();
    await expect(section.getByText("6.0 hours")).toBeVisible();
    await expect(section.getByText("High", { exact: true })).toBeVisible();
    await expect(section.getByText("water:load", { exact: true })).not.toBeVisible();
    await section.getByText("Technical evidence", { exact: true }).click();
    await expect(section.getByText("water:load", { exact: true })).toBeVisible();
    await expect(section.getByText("water-flow / cooling-load")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    await section.screenshot({ path: `test-results/measurable-consequence-${width}.png` });
    await page.getByRole("button", { name: "Open investigation" }).click();
    await page.getByRole("button", { name: "Open evidence record" }).click();
    await expect(section.getByText("12,840 gal")).toBeVisible();
  });
}

test("insufficient consequence remains explicit in canonical Findings review", async ({ page }) => {
  await openMeasuredFinding(page, { status: "not_quantifiable", statement: "Consequence not quantifiable from available evidence." });
  const section = page.getByRole("region", { name: "Measurable consequence" });
  await expect(section.getByText("Consequence not quantifiable from available evidence.")).toBeVisible();
  await expect(section.getByText("0 gal")).toHaveCount(0);
});
