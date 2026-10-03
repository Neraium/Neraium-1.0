import { expect, test } from "@playwright/test";
import { governedComparisonResult } from "./fixtures.js";

test.use({ actionTimeout: 15000 });

const result = governedComparisonResult({
  job_id: "ux-phase4",
  facility_name: "North Plant",
  sii_completed: true,
  sii_reliable_enough_to_show: true,
  evidence_persisted: true,
  drift_metrics: { baseline_distance: 0.7 },
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

async function mockApi(page) {
  const currentUpload = { job_id: result.job_id, filename: "cooling.csv", status: "complete", result };
  const latestUpload = { status: "complete", session_state: "verified", sii_completed: true, latest_result: result, current_upload: currentUpload, snapshot: { status: "complete", sii_completed: true, current_upload: currentUpload, latest_result: result } };
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/api/")) return route.continue();
    const payloads = {
      "/api/auth/me": { authenticated: true, user: { email: "phase4@example.test", role: "admin" }, workspaces: [{ workspace_id: "default", display_name: "North Plant", is_active: true }], default_workspace_id: "default" },
      "/api/data/analyses/ux-phase4": result,
      "/api/data/latest-upload": latestUpload,
      "/api/evidence/runs": { runs: [] },
      "/api/findings": { findings: [], has_more: false },
      "/api/facility/context": { systems: [{ system_id: "cooling", name: "Cooling system" }], equipment: [], timezone: "UTC" },
      "/api/facility/systems": { systems: [] },
      "/api/data-connections": { connections: [] },
      "/api/data-connections/providers": { providers: [] },
      "/api/data-connections/signal-concepts": { concepts: [] },
    };
    return route.fulfill({ status: 200, json: payloads[path] ?? {} });
  });
}

for (const width of [320, 1440]) {
  test(`evidence disclosures and historical review actions at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockApi(page);
    await page.goto("/analyses/ux-phase4");
    await page.getByRole("button", { name: "Review finding", exact: true }).click();
    await page.getByRole("button", { name: "Open investigation", exact: true }).click();
    const comparison = page.getByText(/All relationship evidence/);
    await expect(comparison).toBeVisible();
    const arrowStyle = () => comparison.evaluate((node) => {
      const style = getComputedStyle(node, "::after");
      return { content: style.content, transform: style.transform, width: style.width };
    });
    const collapsed = await arrowStyle();
    expect(collapsed.content).toBe('""');
    expect(collapsed.width).toBe("7px");
    await comparison.focus();
    await page.keyboard.press("Enter");
    await expect(comparison.locator("..")).toHaveAttribute("open", "");
    await expect.poll(async () => (await arrowStyle()).transform).not.toBe(collapsed.transform);
    await page.getByRole("button", { name: "Open evidence record", exact: true }).click();
    const audit = page.getByText("Technical evidence and audit trail", { exact: true });
    await audit.focus();
    await page.keyboard.press("Enter");
    await expect(audit.locator("..")).toHaveAttribute("open", "");
    await expect(page.getByRole("heading", { name: "Record identity", exact: true })).toBeVisible();
    if (width <= 1024) await page.getByRole("button", { name: "Open menu", exact: true }).click();
    await page.getByRole("navigation", { name: "Primary navigation" }).getByRole("button", { name: "Historical review", exact: true }).click();
    await page.getByRole("button", { name: "Review Details", exact: true }).click();
    const details = page.getByText("Analysis Details", { exact: true });
    await expect(details).toBeFocused();
    await expect(details.locator("..")).toHaveAttribute("open", "");
    await expect(details).toBeInViewport();
    await details.click();
    await page.getByRole("button", { name: "Review Evidence", exact: true }).click();
    await expect(details).toBeFocused();
    await expect(details.locator("..")).toHaveAttribute("open", "");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
  });
}

test("mobile keyboard navigation includes facility selection", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 600 });
  await mockApi(page);
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: {
    authenticated: true, user: { email: "phase4@example.test", role: "operator" },
    workspaces: [{ workspace_id: "default", display_name: "North Plant", is_active: true }, { workspace_id: "south", display_name: "South Plant", is_active: true }],
    default_workspace_id: "default",
  } }));
  await page.goto("/workspace/help");
  await page.getByRole("button", { name: "Open menu", exact: true }).click();
  const selector = page.getByRole("combobox", { name: "Facility workspace" });
  await page.getByRole("navigation", { name: "Primary navigation" }).getByRole("button", { name: "Help & Status", exact: true }).focus();
  await page.keyboard.press("Tab");
  await expect(selector).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Sign out", exact: true })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Work", exact: true })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Shift+Tab");
  await expect(selector).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Open menu", exact: true })).toBeFocused();
});
