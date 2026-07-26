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
      classification: { type: "unexplained_systemic_change", label: "Unexplained systemic change", confidence: "high", reasons: ["Operating context matched strongly.", "The relationship shift remained persistent."], alternative_explanations: ["An undocumented control-state change may still explain the shift."], certainty_limit: "This describes a relationship change and does not establish a cause." },
      data_confidence: { rating: "high", summary: "Telemetry passed recorded quality checks.", reasons: [] },
      operating_mode: { match: "strong", confidence: "high", baseline_mode_label: "Mid-load operation", recent_mode_label: "Mid-load operation", differences: [] },
      sensor_health: [{ signal: "Flow-01", health: "healthy", conditions: [] }],
      persistence: { persistent: true, duration: "3 days", summary: "The relationship shift remained present across comparable windows." },
      investigation_guidance: [{ rank: 1, check: "Verify source data and control-state context.", reason: "Source validation bounds the physical-system interpretation.", category: "data_quality", editable: true }],
      activity_timeline: [{ event_type: "baseline_reference", title: "Baseline reference period", start: "2026-07-19T10:00:00Z", end: "2026-07-20T10:00:00Z", precision: "range" }, { event_type: "persistence_supported", title: "Persistence supported", period_label: "Recent comparison window", precision: "period" }],
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
    await expect(card.locator(".finding-classification__chip")).toHaveCount(3);
    await expect(card.locator(".operational-finding__evidence-line")).toHaveCount(1);
    await expect(card.locator(".operational-finding__next p")).toHaveCount(1);
    await expect(card.getByText("Missing telemetry limits the conclusion.")).toHaveCount(0);
    await expect(card.getByLabel(/Classification: Unexplained systemic change/i)).toBeVisible();
    await expect(card.locator(".finding-classification--systemic")).toBeVisible();
    await expect(card.getByRole("button", { name: "Review" })).toBeVisible();
    await expect(card.getByRole("button", { name: "Acknowledge" })).toBeVisible();

    await card.getByRole("button", { name: "View evidence" }).click();
    await expect(page).toHaveURL(/\/evidence\/flow-response$/);
    await expect(page.getByText("What changed")).toBeVisible();
    await expect(page.getByText("Supporting evidence")).toBeVisible();
    await expect(page.getByText("Highest-value next checks")).toBeVisible();
    await expect(page.getByText("Verify source data and control-state context.")).toBeVisible();
    const details = page.locator("details.evidence-technical");
    await expect(details).not.toHaveAttribute("open", "");
    await details.locator(":scope > summary").click();
    await expect(details.getByText("Historian X was unavailable during the comparison window.")).toBeVisible();
    await details.getByRole("button", { name: "Open trace mode" }).click();
    await expect(page.getByRole("heading", { name: "Trace mode" })).toBeVisible();
  });

  test("mobile uses a vertical answer and keeps evidence before the action", async ({ page }) => {
    await openSite(page, { width: 390, height: 844 });
    const card = page.locator(".operational-finding");
    const metrics = await card.evaluate((node) => {
      const evidence = node.querySelector(".operational-finding__evidence-line")?.getBoundingClientRect();
      const next = node.querySelector(".operational-finding__next")?.getBoundingClientRect();
      const action = node.querySelector(".operational-finding__action")?.getBoundingClientRect();
      const title = node.querySelector(".operational-finding__identity")?.getBoundingClientRect();
      const cardBox = node.getBoundingClientRect();
      return {
        overflow: document.documentElement.scrollWidth - window.innerWidth,
        summaryOrder: Boolean(evidence && next && action && evidence.bottom <= next.top + 1 && next.bottom <= action.top + 1),
        titleUsesCardWidth: Boolean(title && title.width >= cardBox.width - 32),
        actionsFitCard: Boolean(action && action.right <= cardBox.right + 1),
        classificationFits: Boolean(node.querySelector(".finding-classification")?.getBoundingClientRect().right <= window.innerWidth + 1),
      };
    });
    expect(metrics.overflow).toBeLessThanOrEqual(1);
    expect(metrics.summaryOrder).toBe(true);
    expect(metrics.titleUsesCardWidth).toBe(true);
    expect(metrics.actionsFitCard).toBe(true);
    expect(metrics.classificationFits).toBe(true);
  });

  test("asset search opens evidence directly and technical trace stays nested", async ({ page }) => {
    await openSite(page, { width: 1280, height: 800 });
    await page.getByRole("combobox", { name: /Search sites/ }).fill("Chiller-03");
    await page.getByRole("option", { name: "Asset / signal: Chiller-03" }).click();
    await expect(page).toHaveURL(/\/evidence\/flow-response$/);
    await expect(page.getByRole("button", { name: "Open trace mode" })).toHaveCount(0);
    await page.locator("details.evidence-technical > summary").click();
    await expect(page.getByRole("button", { name: "Open trace mode" })).toBeVisible();
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
