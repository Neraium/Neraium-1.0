import { expect, test } from "./fixtures.js";

function findingPayload() {
  const analysis = {
    analysis_id: "drawer-analysis",
    source_file: "drawer-telemetry.csv",
    generated_at: "2026-07-21T10:00:00Z",
    data_quality: { warnings: [] },
    systems: [{ id: "pump-system", name: "Pump system" }],
    relationships: [{ id: "pump-flow", columns: ["pump_power", "flow"], change_type: "weakened" }],
    fingerprint: {
      status: "changed",
      meaning: "Pump behavior moved away from the learned baseline.",
      evidence_refs: ["drawer-evidence"],
    },
    insights: [{
      id: "pump-relationships",
      title: "Pump relationships changed",
      severity: "high",
      confidence: "high",
      confidence_score: 0.91,
      system: "Pump system",
      what_changed: "Pump power and flow stopped moving together like the learned baseline.",
      why_it_matters: "The changed relationship may reduce operating efficiency.",
      recommended_check: "Check pump schedule and valve position",
      contributing_relationships: [{ id: "pump-flow", columns: ["pump_power", "flow"], change_type: "weakened" }],
      evidence_refs: ["drawer-evidence"],
    }],
    evidence_index: {
      "drawer-evidence": {
        evidence_id: "drawer-evidence",
        type: "relationship_change",
        description: "Pump power and flow relationship weakened.",
        supporting_signals: ["Pump power increased", "Flow decreased"],
        source_columns: ["pump_power", "flow"],
        confidence: "high",
        confidence_score: 0.91,
      },
    },
  };
  const result = {
    job_id: "drawer-job",
    filename: "drawer-telemetry.csv",
    processed_at: "2026-07-21T10:00:00Z",
    row_count: 1440,
    sii_reliable_enough_to_show: true,
    sii_completed: true,
    analysis_result: analysis,
    analysis_explanation: analysis,
    baseline_analysis: { status: "available", relationship_drift: analysis.relationships },
    sii_intelligence: {
      facility_state: "needs review",
      baseline: { state: "changed", confidence: 0.82 },
    },
  };
  const currentUpload = {
    job_id: "drawer-job",
    filename: "drawer-telemetry.csv",
    status: "complete",
    result,
  };
  const snapshot = {
    status: "complete",
    session_state: "verified",
    sii_completed: true,
    processed_at: "2026-07-21T10:00:00Z",
    current_upload: currentUpload,
    latest_result: result,
  };
  return {
    status: "complete",
    session_state: "verified",
    sii_completed: true,
    latest_result: result,
    current_upload: currentUpload,
    snapshot,
  };
}

async function routeFinding(page) {
  await page.route("**/api/data/latest-upload**", (route) => {
    const origin = route.request().headers().origin ?? "*";
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: {
        "access-control-allow-origin": origin,
        "access-control-allow-credentials": "true",
      },
      body: JSON.stringify(findingPayload()),
    });
  });
}

async function openCommandCenter(page, viewport, path = "/workspace") {
  await page.setViewportSize(viewport);
  await routeFinding(page);
  await page.goto(path, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  await expect(page.getByRole("button", { name: "Open finding" })).toBeVisible();
}

async function openDrawer(page) {
  await page.getByRole("button", { name: "Open finding" }).click();
  await expect(page.getByRole("dialog", { name: "Pump relationships changed" })).toBeVisible();
}

test.describe("Investigation Drawer responsive behavior", () => {
  for (const viewport of [
    { name: "desktop", width: 1440, height: 900, expectedRatio: 0.63 },
    { name: "tablet", width: 768, height: 1024, expectedRatio: 0.64 },
    { name: "mobile", width: 390, height: 844, expectedRatio: 1 },
  ]) {
    test(`${viewport.name} keeps the expected dashboard and investigation framing`, async ({ page }) => {
      await openCommandCenter(page, viewport);
      await openDrawer(page);
      await expect.poll(async () => {
        const box = await page.locator(".investigation-panel").boundingBox();
        return Math.abs(viewport.width - (box.x + box.width));
      }).toBeLessThanOrEqual(1);

      const metrics = await page.getByTestId("investigation-surface").evaluate((surface) => {
        const panelRect = surface.querySelector(".investigation-panel").getBoundingClientRect();
        const dashboard = document.querySelector("[data-testid='operational-command-center']");
        return {
          panelLeft: panelRect.left,
          panelWidth: panelRect.width,
          viewportWidth: window.innerWidth,
          dashboardMounted: Boolean(dashboard),
          dashboardVisible: dashboard ? getComputedStyle(dashboard).display !== "none" : false,
          backgroundColor: getComputedStyle(surface).backgroundColor,
          documentWidth: document.documentElement.scrollWidth,
        };
      });

      expect(metrics.dashboardMounted).toBe(true);
      expect(metrics.dashboardVisible).toBe(true);
      expect(metrics.documentWidth).toBeLessThanOrEqual(metrics.viewportWidth + 1);
      expect(metrics.panelWidth / metrics.viewportWidth).toBeCloseTo(viewport.expectedRatio, 1);
      if (viewport.name === "mobile") {
        expect(metrics.panelLeft).toBeLessThanOrEqual(1);
      } else {
        expect(metrics.panelLeft).toBeGreaterThan(0);
        expect(metrics.backgroundColor).toMatch(/^rgba\(/);
      }

      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog", { name: "Pump relationships changed" })).toBeHidden();
    });
  }
});

test.describe("Investigation Drawer navigation and context", () => {
  test("supports Close, outside click, Escape, and Browser Back without activating the dashboard", async ({ page }) => {
    await openCommandCenter(page, { width: 1440, height: 900 });

    await openDrawer(page);
    await expect(page.getByRole("button", { name: "Close investigation drawer" })).toBeFocused();
    await page.getByRole("button", { name: "Close investigation drawer" }).click();
    await expect(page).toHaveURL(/\/workspace$/);

    await openDrawer(page);
    await page.keyboard.press("Escape");
    await expect(page).toHaveURL(/\/workspace$/);

    await openDrawer(page);
    await page.evaluate(() => {
      window.__dashboardClickCount = 0;
      document.querySelector("[data-testid='operational-command-center']")
        ?.addEventListener("click", () => { window.__dashboardClickCount += 1; });
    });
    await page.mouse.click(20, 300);
    await expect(page).toHaveURL(/\/workspace$/);
    expect(await page.evaluate(() => window.__dashboardClickCount)).toBe(0);

    await openDrawer(page);
    await page.goBack();
    await expect(page).toHaveURL(/\/workspace$/);
    await expect(page.getByRole("dialog", { name: "Pump relationships changed" })).toBeHidden();
  });

  test("full workspace uses a dedicated route and returns to the exact dashboard context", async ({ page }) => {
    await openCommandCenter(page, { width: 1440, height: 900 }, "/workspace?severity=high&subsystem=pump-system");

    await page.evaluate(() => window.scrollTo(0, Math.min(560, document.documentElement.scrollHeight - window.innerHeight)));
    const scrollBefore = await page.evaluate(() => window.scrollY);
    await page.getByRole("button", { name: "Open finding" }).evaluate((button) => button.click());
    await expect(page.getByRole("dialog", { name: "Pump relationships changed" })).toBeVisible();

    await page.getByRole("button", { name: "Expand investigation to full workspace" }).click();
    await expect(page).toHaveURL(/\/workspace\/investigations\/pump-relationships\?severity=high&subsystem=pump-system$/);
    await expect(page.getByTestId("investigation-surface")).toHaveAttribute("data-investigation-mode", "full");
    await expect(page.getByRole("button", { name: "Close full investigation workspace" })).toBeVisible();

    const fullWidth = await page.locator(".investigation-panel").evaluate((panel) => panel.getBoundingClientRect().width / window.innerWidth);
    expect(fullWidth).toBeGreaterThan(0.99);

    await page.goBack();
    await expect(page).toHaveURL(/\/workspace\?severity=high&subsystem=pump-system$/);
    await expect(page.getByRole("dialog", { name: "Pump relationships changed" })).toBeHidden();
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(scrollBefore);
    expect(await page.evaluate(() => localStorage.getItem("neraium.operational.selected_insight"))).toBe("pump-relationships");
    await expect(page.getByRole("button", { name: "Open finding" })).toBeVisible();
  });

  test("removes drawer motion when reduced motion is requested", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await openCommandCenter(page, { width: 1024, height: 768 });
    await openDrawer(page);

    const durations = await page.locator(".investigation-panel").evaluate((panel) => ({
      panel: getComputedStyle(panel).transitionDuration,
      surface: getComputedStyle(panel.parentElement).transitionDuration,
    }));
    expect(parseFloat(durations.panel)).toBeLessThanOrEqual(0.00001);
    expect(parseFloat(durations.surface)).toBeLessThanOrEqual(0.00001);
  });
});
