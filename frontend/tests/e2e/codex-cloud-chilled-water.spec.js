import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "./fixtures.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const fixtures = path.resolve(here, "../../../test-fixtures/chilled-water");
const RETIRED_UPLOAD_REASON = "Retired: this scenario requires creating historical baseline and comparison uploads, which app.neraium.com no longer exposes as a normal production workflow.";

test("AWS-free chilled-water baseline and persistent pump degradation survive refresh and mobile", async ({ page }) => {
  test.skip(true, RETIRED_UPLOAD_REASON);
  const foreignMarkers = ["commercial water system.csv", "Unassigned Analysis", "Demo Site"];

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  await page.getByRole("button", { name: "Import Historical Dataset", exact: true }).click();
  await page.getByTestId("csv-upload-input").setInputFiles(path.join(fixtures, "chilled-water-baseline.csv"));
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page).toHaveURL(/\/baselines\/[^/]+\/ready$/, { timeout: 120_000 });
  await expect(page.getByRole("heading", { name: "Baseline Established", level: 3 })).toBeVisible();
  await expect(page.getByText("chilled-water-baseline.csv")).toBeVisible();
  const baselineUrl = page.url();
  for (const marker of foreignMarkers) await expect(page.getByText(marker, { exact: false })).toHaveCount(0);

  await page.screenshot({ path: path.resolve(here, "../../../docs/screenshots/codex-cloud-baseline-ready.png"), fullPage: true });
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page).toHaveURL(baselineUrl);
  await expect(page.getByText("chilled-water-baseline.csv")).toBeVisible();

  await page.getByRole("button", { name: "Upload Comparison Dataset" }).click();
  await page.getByTestId("csv-upload-input").setInputFiles(path.join(fixtures, "chilled-water-pump-degradation.csv"));
  await page.getByRole("button", { name: "Evaluate Against Baseline" }).click();

  await expect(page).toHaveURL(/\/analyses\/[^/]+$/, { timeout: 120_000 });
  await expect(page.getByRole("heading", { name: /Pump power \/ Chilled water flow coupling weakened/i }).first()).toBeVisible();
  await expect(page.getByText("1 item in review")).toBeVisible();
  await expect(page.getByText(/Evidence \(\d+\)/).first()).toBeVisible();
  const analysisUrl = page.url();
  const analysisId = new URL(analysisUrl).pathname.split("/").filter(Boolean).at(-1);
  const firstPackageResponse = await page.request.get(`/api/data/analyses/${analysisId}/evidence-package`);
  expect(firstPackageResponse.ok()).toBeTruthy();
  const firstPackage = await firstPackageResponse.json();
  expect(firstPackage.id).toBeTruthy();
  expect(firstPackage.schema_version).toBe("evidence-package-v1");
  expect(firstPackage.revision).toBe(1);
  expect(firstPackage.lifecycle).toMatchObject({
    status: "OPEN",
    provenance: {
      schema_version: "evidence-package-lifecycle-v1",
      source: "lifecycle_event_store",
    },
    events: [{
      actor: "system",
      event_type: "package_created",
      reason: "Evidence Package created from the completed baseline comparison.",
      metadata: {},
    }],
  });
  expect(firstPackage.lifecycle.events).toHaveLength(1);
  expect(new Date(firstPackage.lifecycle.events[0].timestamp).toISOString()).toBe(
    new Date(firstPackage.created_at).toISOString(),
  );
  expect(firstPackage.lifecycle.events[0].event_id).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
  expect(firstPackage.comparison_reference.reference_level).toBe("matched_historical_baseline");
  expect(firstPackage.primary_relationship).toMatchObject({
    relationship_label: "pump_power_kw / chw_flow_gpm",
    change_direction: "weakened",
    baseline_strength: 0.998290,
    comparison_strength: 0.690739,
    absolute_change: 0.307551,
    baseline_sample_count: 672,
    comparison_sample_count: 672,
  });
  expect(firstPackage.operating_context).toMatchObject({
    schema_version: "operating-context-v1",
    comparison_state: {
      state_type: "transitioning",
      state_confidence: { level: "unknown", score: null },
    },
    load_context: {
      canonical_role: "process_demand",
      baseline_mean: 317.33788244,
      comparison_mean: 317.33788244,
      baseline_range: { min: 164.268, max: 515.902 },
      comparison_range: { min: 164.268, max: 515.902 },
    },
    equipment_configuration: [],
    environmental_context: [],
    transition_context: { direction: "mixed" },
    comparability: { level: "high", score: 1 },
  });
  expect(firstPackage.operating_context.control_context[0]).toMatchObject({
    canonical_role: "control_command",
    baseline_mean: 67.83942708,
    comparison_mean: 67.83942708,
  });
  expect(firstPackage.operating_context.baseline_window).toMatchObject({
    start: "2026-06-01T00:00:00",
    end: "2026-06-07T23:45:00",
  });
  expect(firstPackage.operating_context.comparison_window).toMatchObject({
    start: "2026-06-15T00:00:00",
    end: "2026-06-21T23:45:00",
  });
  // The historical trust boundary now supplies deterministic power/flow
  // semantics, so the legacy missing-semantic-mapping limitation is resolved.
  expect(firstPackage.limitations).toEqual([]);
  expect(firstPackage.hypotheses).toEqual([]);
  const immutableAnalyticalEvidence = {
    timeline: firstPackage.timeline,
    supporting_evidence: firstPackage.supporting_evidence,
    confidence: firstPackage.confidence,
    limitations: firstPackage.limitations,
    provenance: firstPackage.provenance,
  };
  for (const marker of foreignMarkers) await expect(page.getByText(marker, { exact: false })).toHaveCount(0);

  await page.screenshot({ path: path.resolve(here, "../../../docs/screenshots/codex-cloud-pump-degradation.png"), fullPage: true });
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page).toHaveURL(analysisUrl);
  await expect(page.getByRole("heading", { name: /Pump power \/ Chilled water flow coupling weakened/i }).first()).toBeVisible();
  const restoredPackage = await (await page.request.get(`/api/data/analyses/${analysisId}/evidence-package`)).json();
  expect(restoredPackage).toEqual(firstPackage);
  expect(restoredPackage.id).toBe(firstPackage.id);
  expect(restoredPackage.revision).toBe(1);
  expect(restoredPackage.lifecycle.status).toBe("OPEN");
  expect(restoredPackage.lifecycle.events[0].event_id).toBe(firstPackage.lifecycle.events[0].event_id);
  expect({
    timeline: restoredPackage.timeline,
    supporting_evidence: restoredPackage.supporting_evidence,
    confidence: restoredPackage.confidence,
    limitations: restoredPackage.limitations,
    provenance: restoredPackage.provenance,
  }).toEqual(immutableAnalyticalEvidence);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByTestId("app-ready-root")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: path.resolve(here, "../../../docs/screenshots/codex-cloud-pump-degradation-iphone.png"), fullPage: true });
});
