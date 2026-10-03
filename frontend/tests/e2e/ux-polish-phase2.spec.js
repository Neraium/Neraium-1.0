import { expect, test } from "@playwright/test";
import { governedComparisonResult } from "./fixtures.js";

test.use({ actionTimeout: 15000 });

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

async function openNavigation(page, width) {
  if (width <= 1024) await page.getByRole("button", { name: "Open menu", exact: true }).click();
  return page.getByRole("navigation", { name: "Primary navigation", exact: true });
}

for (const width of [320, 1440]) {
  test(`shared navigation, Help findings and historical access at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width <= 1024 ? 600 : 900 });
    await mockApi(page);
    await page.goto("/workspace/help");
    await expect(page.getByRole("heading", { name: "Help & status" })).toBeVisible();
    const nav = await openNavigation(page, width);
    await expect(nav.getByRole("button", { name: "Help & Status", exact: true })).toHaveAttribute("aria-current", "page");
    await nav.getByRole("button", { name: "Data", exact: true }).click();
    await expect(page).toHaveURL(/\/workspace\/data-sources$/);
    await expect(page.getByRole("heading", { name: "No telemetry source connected" })).toBeVisible();
    const dataNav = await openNavigation(page, width);
    await expect(dataNav.getByRole("button", { name: "Data", exact: true })).toHaveAttribute("aria-current", "page");
    if (width <= 1024) {
      await page.keyboard.press("Escape");
      await expect(page.getByRole("button", { name: "Open menu", exact: true })).toBeFocused();
      await page.getByRole("button", { name: "Open menu", exact: true }).click();
    }
    await dataNav.getByRole("button", { name: "Help & Status", exact: true }).click();
    await page.getByRole("button", { name: "Open findings", exact: true }).click();
    await expect(page).toHaveURL(/\/findings$/);
    await page.goto("/workspace/help");
    await page.getByRole("main").getByRole("button", { name: "Historical review", exact: true }).click();
    await expect(page).toHaveURL(/\/workspace\/insights$/);
    await expect(page.getByRole("navigation", { name: "Context trail" })).toContainText("Historical review");
    await page.goto("/workspace/help");
    await page.getByRole("main").getByRole("button", { name: "Historical replay", exact: true }).click();
    await expect(page).toHaveURL(/\/workspace\/advanced$/);
    await expect(page.getByRole("navigation", { name: "Context trail" })).toContainText("Historical replay");
    await page.getByRole("navigation", { name: "Context trail" }).getByRole("button", { name: "System Status", exact: true }).click();
    await expect(page).toHaveURL(/\/sites\/current$/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
  });

  test(`finding, investigation and evidence context with honest Back at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockApi(page);
    await page.goto("/analyses/ux-phase1");
    await page.getByRole("button", { name: "Review finding", exact: true }).click();
    await page.getByRole("button", { name: "Open evidence record", exact: true }).click();
    await expect(page.getByTestId("evidence-record")).toBeVisible();
    await page.getByRole("button", { name: "Back", exact: true }).click();
    await expect(page.getByTestId("finding-review")).toBeVisible();
    await page.getByRole("button", { name: "Open investigation", exact: true }).click();
    await expect(page.getByTestId("investigation-workspace")).toBeVisible();
    await page.getByRole("button", { name: "Open evidence record", exact: true }).click();
    const trail = page.getByRole("navigation", { name: "Context trail" });
    await expect(trail.locator('[aria-current="page"]')).toHaveText("Evidence");
    await trail.getByRole("button", { name: "Finding", exact: true }).click();
    await expect(page).toHaveURL(/\/findings\/finding-a$/);
    await expect(page.getByTestId("finding-review")).toBeVisible();
    await page.getByRole("button", { name: "Back", exact: true }).click();
    await expect(page.getByTestId("evidence-record")).toBeVisible();
    await trail.getByRole("button", { name: "Investigation", exact: true }).click();
    await expect(page).toHaveURL(/\/investigations\/finding-a$/);
    await expect(page.getByTestId("investigation-workspace")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
  });
}

test("direct unavailable evidence keeps bounded state and Back fallback", async ({ page }) => {
  await mockApi(page);
  await page.goto("/evidence/missing-finding");
  await expect(page.getByRole("heading", { name: "Evidence record unavailable" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open evidence record", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await expect(page).toHaveURL(/\/investigations$/);
});
