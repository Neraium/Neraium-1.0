import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures.js";

const VIEWPORTS = [
  { name: "desktop-1440", width: 1440, height: 1000 },
  { name: "desktop-1024", width: 1024, height: 768 },
  { name: "iphone-390", width: 390, height: 844 },
  { name: "iphone-430", width: 430, height: 932 },
];

const configurations = {
  configurations: [{
    system_id: "resort-chilled-water",
    enabled: true,
    approved_baseline_id: "bdm-live-1",
    analysis_interval_seconds: 300,
    comparison_window_minutes: 60,
    minimum_coverage_percent: 80,
    allowed_lateness_minutes: 5,
    last_analysis_started_at: "2026-08-01T12:05:00Z",
    last_analysis_completed_at: "2026-08-01T12:05:05Z",
    next_analysis_at: "2026-08-01T12:10:00Z",
    current_status: "enabled",
    latest_error: null,
    created_at: "2026-07-31T12:00:00Z",
    updated_at: "2026-08-01T12:05:05Z",
  }],
};

const telemetry = {
  health: [{
    system_id: "resort-chilled-water",
    source: "historian-rest",
    last_successful_ingestion_at: "2026-08-01T12:09:10Z",
    last_telemetry_timestamp: "2026-08-01T12:09:00Z",
    accepted_count: 480,
    rejected_count: 2,
    latest_error_or_warning: null,
    status: "healthy",
    updated_at: "2026-08-01T12:09:10Z",
  }],
};

const analysisHealth = {
  health: [{
    system_id: "resort-chilled-water",
    last_attempted_run_at: "2026-08-01T12:05:00Z",
    last_completed_run_at: "2026-08-01T12:05:05Z",
    last_successful_run_at: "2026-08-01T12:05:05Z",
    current_status: "healthy",
    current_window_coverage: 96.5,
    latest_skipped_reason: null,
    consecutive_failures: 0,
    latest_error: null,
    next_scheduled_run: "2026-08-01T12:10:00Z",
    updated_at: "2026-08-01T12:05:05Z",
  }],
};

const findings = {
  findings: [{
    finding_id: "live-finding-1",
    deduplication_key: "dedupe-1",
    system_id: "resort-chilled-water",
    relationship_identity: "expected:all_operation:pump_power:flow",
    finding_classification: { type: "unexplained_systemic_change", label: "Unexplained systemic change", certainty_limit: "Root cause was not established." },
    first_detected_at: "2026-08-01T11:02:00Z",
    last_observed_at: "2026-08-01T12:00:00Z",
    opened_at: "2026-08-01T12:05:05Z",
    resolved_at: null,
    current_state: "open",
    persistence_state: { persistent: true, support_fraction: 1 },
    severity_score: 72.5,
    latest_evidence: {
      run_id: "live-run-1",
      source_name: "live:resort-chilled-water",
      rows_accepted: 30,
      evidence_summary: ["pump_power and flow changed from their approved baseline."],
      timestamps: { upload_start: "2026-08-01T11:00:00Z", upload_end: "2026-08-01T12:00:00Z" },
      drift_metrics: { coupling_delta: -0.72 },
      evidence_hash: "evidence-hash-live-1",
    },
    source_live_analysis_run_id: "live-run-1",
    baseline_reference: "bdm-live-1",
    created_at: "2026-08-01T12:05:05Z",
    updated_at: "2026-08-01T12:05:05Z",
  }],
};

const runs = {
  runs: [{
    run_id: "live-run-1",
    system_id: "resort-chilled-water",
    baseline_reference: "bdm-live-1",
    window_start: "2026-08-01T11:00:00Z",
    window_end: "2026-08-01T12:00:00Z",
    status: "completed",
    started_at: "2026-08-01T12:05:00Z",
    completed_at: "2026-08-01T12:05:05Z",
    rows_analyzed: 30,
    signals_analyzed: 2,
    coverage: 96.5,
    skipped_reason: null,
    error_summary: null,
    analytics_result_reference: "live-analysis-result:live-run-1",
    created_findings_count: 1,
    updated_findings_count: 0,
    resolved_findings_count: 0,
    created_at: "2026-08-01T12:05:00Z",
  }],
};

async function mockLiveMonitoring(page) {
  await page.route("**/api/live-analysis/configurations*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(configurations) }));
  await page.route("**/api/telemetry/ingestion-health*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(telemetry) }));
  await page.route("**/api/live-analysis/health*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(analysisHealth) }));
  await page.route("**/api/live-analysis/runs*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(runs) }));
  await page.route("**/api/live-analysis/findings*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(findings) }));
}

async function openLiveMonitoring(page, viewport) {
  await mockLiveMonitoring(page);
  await page.setViewportSize(viewport);
  await page.goto("/workspace/live-monitoring", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("live-monitoring-workspace")).toBeVisible();
}

test.describe("Live Monitoring responsive workspace", () => {
  test("uses the authenticated navigation route", async ({ page }) => {
    await mockLiveMonitoring(page);
    await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "Live Monitoring" }).click();
    await expect(page).toHaveURL(/\/workspace\/live-monitoring$/);
    await expect(page.getByRole("heading", { name: "Live Monitoring", level: 1 })).toBeVisible();
  });

  test("reflows at every required desktop and iPhone viewport", async ({ page }, testInfo) => {
    for (const viewport of VIEWPORTS) {
      await openLiveMonitoring(page, viewport);
      const metrics = await page.evaluate(() => {
        const workspace = document.querySelector("[data-testid='live-monitoring-workspace']")?.getBoundingClientRect();
        return {
          viewport: innerWidth,
          root: document.documentElement.scrollWidth,
          body: document.body.scrollWidth,
          left: workspace?.left,
          right: workspace?.right,
        };
      });
      expect(metrics.root, viewport.name).toBeLessThanOrEqual(metrics.viewport + 1);
      expect(metrics.body, viewport.name).toBeLessThanOrEqual(metrics.viewport + 1);
      expect(metrics.left, viewport.name).toBeGreaterThanOrEqual(0);
      expect(metrics.right, viewport.name).toBeLessThanOrEqual(metrics.viewport + 1);
      await expect(page.getByText("Transport and analysis status only. These states are not equipment findings.")).toBeVisible();
      await expect(page.getByRole("button", { name: "Refresh" })).toBeVisible();
      await page.screenshot({ path: testInfo.outputPath(`live-monitoring-${viewport.name}.png`), fullPage: true });
    }
  });

  test("opens the shared evidence drawer on iPhone", async ({ page }, testInfo) => {
    await openLiveMonitoring(page, { width: 390, height: 844 });
    await page.getByRole("button", { name: "View evidence" }).click();
    const drawer = page.getByRole("dialog", { name: "expected:all_operation:pump_power:flow" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("listitem").filter({ hasText: "pump_power and flow changed from their approved baseline." })).toBeVisible();
    const drawerBox = await drawer.boundingBox();
    expect(drawerBox?.width ?? 999).toBeLessThanOrEqual(390);
    await page.screenshot({ path: testInfo.outputPath("live-monitoring-evidence-390.png") });
    await drawer.getByRole("button", { name: "Close evidence drawer" }).click();
    await expect(drawer).toBeHidden();
  });

  test("passes serious and critical WCAG checks on desktop and iPhone", async ({ page }) => {
    for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
      await openLiveMonitoring(page, viewport);
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
      const violations = results.violations.filter((item) => ["serious", "critical"].includes(item.impact));
      expect(violations.map((item) => ({ id: item.id, targets: item.nodes.map((node) => node.target) }))).toEqual([]);
    }
  });
});
