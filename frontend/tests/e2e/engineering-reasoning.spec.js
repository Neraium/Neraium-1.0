import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures.js";

function reasoningPayload() {
  const analysis = {
    analysis_id: "forensic-analysis",
    generated_at: "2026-07-22T10:00:00Z",
    systems: [{ id: "hydronic", name: "Flow & Pressure" }],
    relationships: [{ id: "chiller-flow", columns: ["Chiller-03", "Flow-01"], change_type: "weakened", baseline_strength: 0.82, current_strength: 0.41, confidence: "qualified" }],
    insights: [{
      id: "flow-response", title: "Flow response changed", confidence: "high", system: "Flow & Pressure",
      what_changed: "Flow response weakened under comparable demand.",
      why_it_matters: "The mapped subsystem response is less stable than the learned comparison.",
      recommended_check: "Review the Chiller-03 and Flow-01 trend overlay.",
      confirmation_criteria: "A comparable operating window should reproduce or rule out the relationship shift.",
      variables: ["Chiller-03", "Flow-01"],
      supporting_evidence: ["Flow response weakened in the current window.", "The mapped relationship moved below its learned range."],
      contributing_relationships: [{ id: "chiller-flow", columns: ["Chiller-03", "Flow-01"], change_type: "weakened", baseline_strength: 0.82, current_strength: 0.41 }],
    }],
  };
  const result = {
    job_id: "forensic-job", facility_name: "North Plant", filename: "governed-telemetry.csv", processed_at: "2026-07-22T10:00:00Z",
    sii_reliable_enough_to_show: true, sii_completed: true, data_quality: { coverage_percent: 82, warnings: ["Historian X was unavailable from 1:10 PM to 3:05 PM."] },
    data_gaps: [{ id: "gap-1", source: "Historian X", duration: "1h 55m", signals: ["Flow-01"], overlaps_change_window: true }],
    replay_timeline: { timeline: [{ timestamp: "2026-07-19T10:00:00Z" }, { timestamp: "2026-07-22T10:00:00Z" }] },
    analysis_result: analysis, analysis_explanation: analysis, baseline_analysis: { status: "available", relationship_drift: analysis.relationships },
    sii_intelligence: { facility_state: "needs review", baseline: { state: "changed" } },
    governance_boundary: { statement: "Raw telemetry remains at this site.", status: "Applied", policy_id: "site-policy" },
  };
  const currentUpload = { job_id: result.job_id, filename: result.filename, status: "complete", result };
  return { status: "complete", session_state: "verified", sii_completed: true, latest_result: result, current_upload: currentUpload, snapshot: { status: "complete", sii_completed: true, current_upload: currentUpload, latest_result: result } };
}

async function routeEvidence(page) {
  await page.route("**/api/data/latest-upload**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(reasoningPayload()) }));
}

async function openPortfolio(page, viewport) {
  await page.setViewportSize(viewport);
  await routeEvidence(page);
  await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("engineering-reasoning-platform")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Where does the evidence warrant attention/i })).toBeVisible();
}

test.describe("Engineering reasoning platform", () => {
  test("desktop follows portfolio to site to evidence-first investigation", async ({ page }) => {
    await openPortfolio(page, { width: 1440, height: 900 });
    await expect(page.getByRole("table")).toBeVisible();
    await page.getByRole("button", { name: /North Plant/ }).hover();
    await expect(page.getByText("Raw telemetry remains at this site.").last()).toBeVisible();
    await page.getByRole("row", { name: /North Plant/ }).getByRole("button", { name: "Open site" }).click();
    await expect(page).toHaveURL(/\/sites\/current$/);
    await expect(page.getByText("Where should I spend the next hour?")).toBeVisible();
    await expect(page.getByText("Flow response changed")).toHaveCount(1);
    await expect(page.getByText("Contradicting or limiting evidence")).toBeVisible();
    await page.getByRole("button", { name: "Open investigation" }).click();
    await expect(page).toHaveURL(/\/investigations\/flow-response$/);
    await expect(page.getByRole("heading", { name: "Behavioral constellation" })).toBeVisible();
    await expect(page.getByRole("slider", { name: /Relationship comparison time/ })).toBeVisible();
    await expect(page.getByRole("dialog")).toContainText("Raw observation");
    await expect(page.getByRole("dialog")).toContainText("Limitations");
    await expect(page.getByText(/Read-only intelligence/).first()).toBeVisible();
    await expect(page.getByText("View relationship table")).toBeVisible();
  });

  test("asset search isolates mapped context and trace remains read-only", async ({ page }) => {
    await openPortfolio(page, { width: 1280, height: 800 });
    await page.getByRole("combobox", { name: /Search sites/ }).fill("Chiller-03");
    await page.getByRole("button", { name: "Asset / signal: Chiller-03" }).click();
    await expect(page).toHaveURL(/\/investigations\/flow-response$/);
    await page.getByRole("button", { name: "Open trace mode" }).click();
    await expect(page).toHaveURL(/\/trace$/);
    await expect(page.getByRole("heading", { name: "Reproducible conclusion lineage" })).toBeVisible();
    await expect(page.getByText("Observation").first()).toBeVisible();
    await expect(page.getByText("Recommendation").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "PDF" })).toBeVisible();
    const prohibited = ["Acknowledge", "Snooze", "Silence", "Reset", "Start", "Stop", "Setpoint"];
    const body = await page.locator("body").innerText();
    for (const label of prohibited) expect(body).not.toContain(label);
  });

  test("mobile investigation uses a bottom-sheet drawer without horizontal overflow", async ({ page }) => {
    await openPortfolio(page, { width: 390, height: 844 });
    await page.getByRole("combobox", { name: /Search sites/ }).fill("Chiller-03");
    await page.getByRole("button", { name: "Asset / signal: Chiller-03" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    const metrics = await page.evaluate(() => {
      const drawer = document.querySelector(".investigation-evidence-rail")?.getBoundingClientRect();
      return { viewport: window.innerWidth, documentWidth: document.documentElement.scrollWidth, bodyWidth: document.body.scrollWidth, drawerLeft: drawer?.left, drawerRight: drawer?.right, drawerBottom: drawer?.bottom, viewportHeight: window.innerHeight };
    });
    expect(metrics.documentWidth).toBeLessThanOrEqual(metrics.viewport + 1);
    expect(metrics.bodyWidth).toBeLessThanOrEqual(metrics.viewport + 1);
    expect(metrics.drawerLeft).toBeGreaterThanOrEqual(-1);
    expect(metrics.drawerRight).toBeLessThanOrEqual(metrics.viewport + 1);
    expect(metrics.drawerBottom).toBeLessThanOrEqual(metrics.viewportHeight + 1);
    await page.getByRole("button", { name: "Close evidence drawer" }).click();
    await expect(page.getByRole("slider", { name: /Relationship comparison time/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "Inspect supporting evidence" })).toBeVisible();
  });

  test("desktop and mobile surfaces have no serious accessibility violations", async ({ page }) => {
    for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
      await openPortfolio(page, viewport);
      const results = await new AxeBuilder({ page }).analyze();
      const serious = results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact));
      expect(serious, serious.map((item) => `${item.id}: ${item.help}`).join("\n")).toEqual([]);
    }
  });

  test("reduced motion removes analytical transitions", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await openPortfolio(page, { width: 1280, height: 800 });
    const durations = await page.locator(".site-bubble").first().evaluate((node) => ({ transition: getComputedStyle(node).transitionDuration, animation: getComputedStyle(node).animationDuration }));
    expect(parseFloat(durations.transition || "0")).toBeLessThanOrEqual(0.001);
    expect(parseFloat(durations.animation || "0")).toBeLessThanOrEqual(0.001);
  });
});
