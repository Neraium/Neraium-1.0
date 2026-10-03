import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { governedComparisonResult } from "./fixtures.js";

const result = governedComparisonResult({
  job_id: "ux-phase1",
  facility_name: "North Plant",
  sii_completed: true,
  sii_reliable_enough_to_show: true,
  evidence_persisted: true,
  data_quality: { coverage_percent: 100 },
  analysis_result: {
    systems: [{ id: "cooling", name: "Cooling system" }],
    relationships: [],
    insights: [{
      id: "finding-a", title: "Cooling relationship changed", system: "Cooling system",
      confidence: "high", what_changed: "Flow and power changed under comparable operation.",
      variables: ["flow", "power"], supporting_evidence: ["The relationship differs from the recorded baseline."],
      contributing_relationships: [{ id: "flow-power", columns: ["flow", "power"], baseline_strength: 0.8, current_strength: 0.4 }],
      certainty_limit: "The evidence does not establish a cause.",
      finding_confidence_v1: {
        change_detection: { level: "high" }, persistence: { status: "persistent" },
        evidence_quality: { level: "high" }, operating_context: { level: "high" },
        relationship_comparison: { metric: "pearson_correlation", baseline_value: 0.8, current_value: 0.4, signed_change: -0.4, absolute_change: 0.4, direction: "decreased" },
      },
    }],
  },
});

async function mockApi(page, registryStatus = 200) {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/api/")) return route.continue();
    const payloads = {
      "/api/auth/me": { authenticated: true, user: { email: "phase1@example.test", role: "admin" }, workspaces: [{ workspace_id: "default", display_name: "North Plant", is_active: true }], default_workspace_id: "default" },
      "/api/data/analyses/ux-phase1": result,
      "/api/data/latest-upload": { status: "empty", session_state: "empty", latest_result: null, snapshot: { status: "empty" } },
      "/api/evidence/runs": { runs: [] },
      "/api/findings": { findings: [], has_more: false },
      "/api/facility/context": { systems: [{ system_id: "cooling", name: "Cooling system" }], equipment: [], timezone: "UTC" },
      "/api/facility/systems": { systems: [] },
      "/api/data-connections": { connections: [] },
      "/api/data-connections/providers": { providers: [] },
      "/api/data-connections/signal-concepts": { concepts: [] },
    };
    return route.fulfill({ status: path === "/api/data-connections" ? registryStatus : 200, json: path === "/api/data-connections" && registryStatus !== 200 ? { detail: "Connection service unavailable." } : payloads[path] ?? {} });
  });
}

async function expectAccessibleReflow(page) {
  const widths = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client + 1);
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(results.violations.filter((item) => ["serious", "critical"].includes(item.impact))).toEqual([]);
}

for (const width of [320, 390, 1440]) {
  test(`finding actions and keyboard route focus at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockApi(page);
    await page.goto("/analyses/ux-phase1");
    await page.getByRole("button", { name: "Review finding", exact: true }).click();
    const main = page.getByRole("main", { name: "Neraium operational workspace" });
    await expect(main).toBeFocused();
    const investigation = page.getByRole("button", { name: "Open investigation", exact: true });
    await expect(investigation).toBeVisible();
    const box = await investigation.boundingBox();
    expect(box.y + box.height).toBeLessThan(900);
    await expectAccessibleReflow(page);
    await page.getByRole("button", { name: "Open evidence record", exact: true }).focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/evidence\/finding-a$/);
    await expect(page.getByTestId("evidence-record")).toBeVisible();
    await expect(main).toBeFocused();
    await page.goBack();
    await expect(page.getByTestId("finding-review")).toBeVisible();
    await expect(main).toBeFocused();
  });

  test(`connection registry and setup states at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockApi(page, 503);
    await page.goto("/workspace/data-sources");
    await expect(page.getByRole("heading", { name: "Connections could not be loaded" })).toBeVisible();
    await expect(page.getByText("0 configured")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "No telemetry source connected" })).toHaveCount(0);
    await expectAccessibleReflow(page);
    await page.unroute("**/api/**");
    await mockApi(page);
    await page.reload();
    await expect(page.getByRole("heading", { name: "No telemetry source connected" })).toBeVisible();
    await expect(page.getByText("0 configured")).toBeVisible();
    await expect(page.locator('.telemetry-setup-path [aria-current="step"]')).toHaveCount(1);
    await expect(page.getByText("Step 1 of 9: Add data source", { exact: true })).toBeVisible();
    const addSource = page.locator(".telemetry-empty").getByRole("button", { name: "Add data source" });
    await expect(addSource).toHaveClass(/command-button/);
    await addSource.click();
    await expect(page.getByRole("heading", { name: "Add a read-only data source" })).toBeVisible();
    await expectAccessibleReflow(page);
  });
}
