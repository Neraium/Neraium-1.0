import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "./fixtures.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const fixtures = path.resolve(here, "../../../test-fixtures/chilled-water");

test("AWS-free chilled-water baseline and persistent pump degradation survive refresh and mobile", async ({ page }) => {
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
  await expect(page.getByRole("heading", { name: /Pump response weakening in Pumping System/i }).first()).toBeVisible();
  await expect(page.getByText("1 item in review")).toBeVisible();
  await expect(page.getByText(/Evidence \(\d+\)/).first()).toBeVisible();
  const analysisUrl = page.url();
  const analysisId = new URL(analysisUrl).pathname.split("/").filter(Boolean).at(-1);
  const firstPackageResponse = await page.request.get(`/api/data/analyses/${analysisId}/evidence-package`);
  expect(firstPackageResponse.ok()).toBeTruthy();
  const firstPackage = await firstPackageResponse.json();
  expect(firstPackage.id).toBeTruthy();
  expect(firstPackage.schema_version).toBe("evidence-package-v1");
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
  expect(firstPackage.limitations).toEqual([]);
  expect(firstPackage.hypotheses).toEqual([]);
  for (const marker of foreignMarkers) await expect(page.getByText(marker, { exact: false })).toHaveCount(0);

  await page.screenshot({ path: path.resolve(here, "../../../docs/screenshots/codex-cloud-pump-degradation.png"), fullPage: true });
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page).toHaveURL(analysisUrl);
  await expect(page.getByRole("heading", { name: /Pump response weakening in Pumping System/i }).first()).toBeVisible();
  const restoredPackage = await (await page.request.get(`/api/data/analyses/${analysisId}/evidence-package`)).json();
  expect(restoredPackage.id).toBe(firstPackage.id);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByTestId("app-ready-root")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: path.resolve(here, "../../../docs/screenshots/codex-cloud-pump-degradation-iphone.png"), fullPage: true });
});
