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
      why_it_matters: "The mapped subsystem response differs from the learned comparison.",
      variables: ["Chiller-03", "Flow-01"],
      supporting_evidence: ["Flow response decreased 12.4%.", "Pump demand increased 6.1%.", "The relationship moved outside its learned range."],
      contributing_relationships: [{ id: "chiller-flow", columns: ["Chiller-03", "Flow-01"], change_type: "weakened", baseline_strength: 0.82, current_strength: 0.41 }],
    }],
  };
  const result = {
    job_id: "forensic-job", facility_name: "North Plant", filename: "governed-telemetry.csv", processed_at: "2026-07-22T10:00:00Z",
    sii_reliable_enough_to_show: true, sii_completed: true, data_quality: { coverage_percent: 82, warnings: ["Historian X was unavailable during the comparison window."] },
    data_gaps: [{ id: "gap-1", source: "Historian X", duration: "1h 55m", signals: ["Flow-01"], overlaps_change_window: true }],
    replay_timeline: { timeline: [{ timestamp: "2026-07-19T10:00:00Z" }, { timestamp: "2026-07-22T10:00:00Z" }] },
    analysis_result: analysis, analysis_explanation: analysis, baseline_analysis: { status: "available", relationship_drift: analysis.relationships },
  };
  const currentUpload = { job_id: result.job_id, filename: result.filename, status: "complete", result };
  return { status: "complete", session_state: "verified", sii_completed: true, latest_result: result, current_upload: currentUpload, snapshot: { status: "complete", sii_completed: true, current_upload: currentUpload, latest_result: result } };
}

async function openSite(page, viewport) {
  await page.setViewportSize(viewport);
  await page.route("**/api/data/latest-upload**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(reasoningPayload()) }));
  await page.route("**/api/evidence/runs**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ runs: [] }) }));
  await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("engineering-reasoning-platform")).toBeVisible();
  await expect(page.getByRole("heading", { name: "North Plant" })).toBeVisible();
  await expect(page.locator(".operational-finding")).toBeVisible();
}

test.describe("Engineering reasoning decision cards", () => {
  test("one site opens directly to a compact operational answer and evidence", async ({ page }) => {
    await openSite(page, { width: 1440, height: 900 });
    await expect(page.getByText("1 behavioral change detected")).toBeVisible();
    const card = page.locator(".operational-finding");
    await expect(card).toHaveCount(1);
    await expect(card.getByRole("heading", { name: "Pump demand no longer matches flow" })).toBeVisible();
    await expect(card.getByText("North Plant · Flow & Pressure")).toBeVisible();
    await expect(card.getByText("Narrowed")).toBeVisible();
    await expect(card.locator(".operational-finding__evidence li")).toHaveCount(3);
    await expect(card.getByText("Missing telemetry limits the conclusion.")).toBeVisible();

    await card.getByRole("button", { name: "Open Evidence" }).click();
    await expect(page).toHaveURL(/\/evidence\/flow-response$/);
    await expect(page.getByText("What changed")).toBeVisible();
    await expect(page.getByText("Supporting evidence")).toBeVisible();
    const details = page.locator("details.evidence-technical");
    await expect(details).not.toHaveAttribute("open", "");
    await details.locator(":scope > summary").click();
    await expect(details.getByText("Historian X was unavailable during the comparison window.")).toBeVisible();
    await details.getByRole("button", { name: "Open Trace Mode" }).click();
    await expect(page.getByRole("heading", { name: "Trace Mode" })).toBeVisible();
  });

  test("mobile uses a vertical answer and keeps evidence before the action", async ({ page }) => {
    await openSite(page, { width: 390, height: 844 });
    const card = page.locator(".operational-finding");
    const metrics = await card.evaluate((node) => {
      const evidence = node.querySelector(".operational-finding__evidence")?.getBoundingClientRect();
      const action = node.querySelector(".operational-finding__action")?.getBoundingClientRect();
      const title = node.querySelector(".operational-finding__what")?.getBoundingClientRect();
      const cardBox = node.getBoundingClientRect();
      return {
        overflow: document.documentElement.scrollWidth - window.innerWidth,
        evidenceBeforeAction: Boolean(evidence && action && evidence.bottom <= action.top + 1),
        titleUsesCardWidth: Boolean(title && title.width >= cardBox.width - 32),
        actionVisible: Boolean(action && action.bottom <= window.innerHeight),
      };
    });
    expect(metrics.overflow).toBeLessThanOrEqual(1);
    expect(metrics.evidenceBeforeAction).toBe(true);
    expect(metrics.titleUsesCardWidth).toBe(true);
    expect(metrics.actionVisible).toBe(true);
  });

  test("asset search opens evidence directly and technical trace stays nested", async ({ page }) => {
    await openSite(page, { width: 1280, height: 800 });
    await page.getByRole("combobox", { name: /Search sites/ }).fill("Chiller-03");
    await page.getByRole("button", { name: "Asset / signal: Chiller-03" }).click();
    await expect(page).toHaveURL(/\/evidence\/flow-response$/);
    await expect(page.getByRole("button", { name: "Open Trace Mode" })).toHaveCount(0);
    await page.locator("details.evidence-technical > summary").click();
    await expect(page.getByRole("button", { name: "Open Trace Mode" })).toBeVisible();
  });

  test("desktop and mobile decision surfaces have no serious accessibility violations", async ({ page }) => {
    for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
      await openSite(page, viewport);
      const results = await new AxeBuilder({ page }).include("#forensic-main").analyze();
      const serious = results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact));
      expect(serious, serious.map((item) => `${item.id}: ${item.help}`).join("\n")).toEqual([]);
    }
  });
});
