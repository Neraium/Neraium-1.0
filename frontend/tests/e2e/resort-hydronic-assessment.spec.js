import { expect, test } from "./fixtures.js";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const fixtureDirectory = path.resolve(process.cwd(), "../tests/fixtures/resort_hydronic");
const baselinePath = path.join(fixtureDirectory, "resort-tower-baseline.csv");
const comparisonPath = path.join(fixtureDirectory, "resort-tower-comparison.csv");
const generationMetadataPath = path.join(fixtureDirectory, "generation-metadata.json");
const hiddenEventPath = path.join(fixtureDirectory, "hidden-event.json");
const artifactDirectory = path.resolve(process.cwd(), "../artifacts/neraium-resort-hydronic");
const reportPath = path.join(artifactDirectory, "neraium-resort-hydronic-pilot-report.html");
const evidencePath = path.join(artifactDirectory, "neraium-resort-hydronic-evidence.csv");
const runSummaryPath = path.join(artifactDirectory, "browser-run-summary.json");

const SIGNAL_MAPPING = [
  { column: "outdoor_air_temp_f", name: "Outdoor air temperature", unit: "°F", role: "context" },
  { column: "system_load_tons", name: "System load", unit: "ton", role: "input" },
  { column: "pump_speed_pct", name: "Pump speed", unit: "%", role: "input" },
  { column: "pump_power_kw", name: "Pump power", unit: "kW", role: "input" },
  { column: "loop_flow_gpm", name: "Loop flow", unit: "gpm", role: "response" },
  { column: "differential_pressure_psi", name: "Differential pressure", unit: "psi", role: "response" },
  { column: "critical_valve_position_pct", name: "Critical valve position", unit: "%", role: "input" },
  { column: "supply_water_temp_f", name: "Supply water temperature", unit: "°F", role: "response" },
  { column: "return_water_temp_f", name: "Return water temperature", unit: "°F", role: "response" },
  { column: "tower_enable_status", name: "Tower enable status", unit: "binary", role: "mode" },
];

function responseFor(response, suffix, method) {
  const url = new URL(response.url());
  return url.pathname.endsWith(suffix) && response.request().method() === method;
}

function asDateTimeLocal(isoTimestamp) {
  return new Date(isoTimestamp).toISOString().slice(0, 16);
}

function median(values) {
  const ordered = [...values].sort((left, right) => left - right);
  if (!ordered.length) return Number.NaN;
  const middle = Math.floor(ordered.length / 2);
  return ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2;
}

function nearMissingPeriod(timestamp, periods, paddingMinutes = 60) {
  const value = Date.parse(timestamp);
  const padding = paddingMinutes * 60_000;
  return periods.some((period) => (
    value >= Date.parse(period.start) - padding
    && value <= Date.parse(period.end) + padding
  ));
}

async function beginFreshAssessment(page) {
  const latestAssessment = page.waitForResponse(
    (response) => responseFor(response, "/api/pilot-assessments", "GET"),
    { timeout: 30_000 },
  ).catch(() => null);
  await page.goto("/data", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("golden-nugget-assessment")).toBeVisible();
  await latestAssessment;
  const startNew = page.getByRole("button", { name: "Start new assessment" });
  if (await startNew.isVisible().catch(() => false)) {
    await startNew.click();
  }
  await expect(page.getByRole("heading", { name: "Upload two distinct operating periods" })).toBeVisible();
}

async function mapAllSignals(page) {
  await page.getByLabel("Baseline timestamp").selectOption("timestamp");
  await page.getByLabel("Comparison timestamp").selectOption("timestamp");
  for (const signal of SIGNAL_MAPPING) {
    const row = page.locator(".golden-mapping-row").filter({
      has: page.getByLabel(`Signal name for ${signal.column}`),
    });
    await expect(row, `mapping row for ${signal.column}`).toHaveCount(1);
    const checkbox = row.locator('input[type="checkbox"]');
    if (!(await checkbox.isChecked())) await checkbox.check();
    await row.locator("select").nth(0).selectOption(signal.column);
    await row.locator('input:not([type="checkbox"])').nth(0).fill(signal.name);
    await row.locator('input:not([type="checkbox"])').nth(1).fill(signal.unit);
    await row.locator('input:not([type="checkbox"])').nth(2).fill("Resort Tower Hydronic Loop");
    await row.locator("select").nth(1).selectOption(signal.role);
  }
}

test.describe("Resort tower hydronic historical assessment", () => {
  test("runs the blinded production workflow from CSV intake through report export", async ({ page }) => {
    test.setTimeout(240_000);
    await mkdir(artifactDirectory, { recursive: true });
    const generationMetadata = JSON.parse(await readFile(generationMetadataPath, "utf8"));
    let hiddenEventWasRead = false;
    let analysisLocked = false;

    await beginFreshAssessment(page);

    await page.getByLabel("Baseline period CSV").setInputFiles(baselinePath);
    await page.getByLabel("Later comparison period CSV").setInputFiles(comparisonPath);
    const intakeResponsePromise = page.waitForResponse(
      (response) => responseFor(response, "/api/pilot-assessments/intake", "POST"),
    );
    await page.getByRole("button", { name: "Inspect datasets" }).click();
    const intakeResponse = await intakeResponsePromise;
    expect(intakeResponse.status()).toBe(201);
    const intake = await intakeResponse.json();

    expect(intake.datasets.baseline.filename).toBe(path.basename(baselinePath));
    expect(intake.datasets.comparison.filename).toBe(path.basename(comparisonPath));
    expect(intake.datasets.baseline.rows).toBe(generationMetadata.baseline.written_rows);
    expect(intake.datasets.comparison.rows).toBe(generationMetadata.comparison.written_rows);
    expect(intake.event_backtest).toBeNull();
    expect(hiddenEventWasRead).toBe(false);
    await expect(page.getByText(`${path.basename(baselinePath)} → ${path.basename(comparisonPath)}`)).toBeVisible();
    await expect(page.getByText("Known event remains hidden")).toBeVisible();
    await expect(page.getByLabel("Known event timestamp (UTC)")).toHaveCount(0);

    await mapAllSignals(page);
    const mappingResponsePromise = page.waitForResponse(
      (response) => response.url().includes(`/api/pilot-assessments/${intake.assessment_id}/mapping`)
        && response.request().method() === "PUT",
    );
    await page.getByRole("button", { name: "Validate mapping" }).click();
    const mappingResponse = await mappingResponsePromise;
    expect(mappingResponse.ok()).toBeTruthy();
    const mapped = await mappingResponse.json();
    expect(mapped.mapping_validation.ready).toBe(true);
    expect(mapped.mapping_validation.errors).toEqual([]);
    expect(mapped.mapping.signals.filter((signal) => signal.include)).toHaveLength(SIGNAL_MAPPING.length);
    expect(new Set(mapped.mapping.signals.map((signal) => signal.system_name))).toEqual(
      new Set(["Resort Tower Hydronic Loop"]),
    );
    await expect(page.getByText("Mapping ready")).toBeVisible();

    expect(hiddenEventWasRead).toBe(false);
    await expect(page.getByLabel("Known event timestamp (UTC)")).toHaveCount(0);
    const analysisResponsePromise = page.waitForResponse(
      (response) => response.url().includes(`/api/pilot-assessments/${intake.assessment_id}/analyze`)
        && response.request().method() === "POST",
      { timeout: 120_000 },
    );
    await page.getByRole("button", { name: "Run blinded analysis" }).click();
    const analysisResponse = await analysisResponsePromise;
    expect(analysisResponse.ok()).toBeTruthy();
    const analyzed = await analysisResponse.json();
    analysisLocked = ["analysis_complete", "baseline_withheld"].includes(analyzed.status);

    expect(analysisLocked).toBe(true);
    expect(hiddenEventWasRead).toBe(false);
    expect(analyzed.event_backtest).toBeNull();
    expect(analyzed.analysis.event_timestamp_used).toBe(false);
    expect(analyzed.quality_gate.passed).toBe(true);
    expect(analyzed.quality_gate.decision).toBe("baseline_accepted");
    expect(analyzed.quality_gate.warnings.some((warning) => /duplicate baseline timestamps were excluded/i.test(warning))).toBe(true);
    expect(analyzed.operating_modes.length).toBeGreaterThan(0);
    expect(analyzed.operating_modes.some((mode) => mode.comparable && mode.used_for_findings)).toBe(true);
    expect(analyzed.operating_modes.find((mode) => mode.mode === "startup")?.baseline_records).toBeGreaterThan(0);
    expect(analyzed.operating_modes.find((mode) => mode.mode === "shutdown")?.comparison_records).toBeGreaterThan(0);
    expect(analyzed.analysis.finding_count).toBeGreaterThanOrEqual(1);

    await expect(page.getByText("Baseline accepted", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Like-for-like operating modes" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Data quality notes" })).toBeVisible();
    await expect(page.getByText("7 duplicate baseline timestamps were excluded", { exact: true })).toBeVisible();
    await expect(page.getByText("Tower-enable coverage was limited during the comparison period", { exact: true })).toBeVisible();

    const finding = analyzed.analysis.findings[0];
    expect(finding.title).toBe("Pump demand no longer matches expected flow response");
    expect(finding.first_surfaced_at).toBeTruthy();
    expect(finding.evidence_count).toBe(finding.relationships.length);
    expect(finding.evidence_count).toBeGreaterThan(0);
    await expect(page.getByRole("heading", { name: finding.title, exact: true })).toBeVisible();
    await expect(page.getByText("The system required a different level of pump demand to produce the hydraulic response learned during the baseline period.", { exact: true })).toBeVisible();
    await expect(page.getByText(`${finding.evidence_count} supporting relationship changes`, { exact: true })).toBeVisible();
    const evidenceButton = page.getByRole("button", { name: "View relationship evidence" }).first();
    await evidenceButton.click();
    const firstRelationship = finding.relationships[0];
    await expect(page.getByRole("heading", { name: firstRelationship.relationship, exact: true }).first()).toBeVisible();

    const evidenceDownloadPromise = page.waitForEvent("download");
    await page.getByRole("link", { name: /^Exact records \(/ }).first().click();
    const evidenceDownload = await evidenceDownloadPromise;
    await evidenceDownload.saveAs(evidencePath);
    const evidenceCsv = await readFile(evidencePath, "utf8");
    expect(evidenceCsv).toContain("period,source_row,timestamp,operating_mode");
    expect(evidenceCsv).toContain("baseline");
    expect(evidenceCsv).toContain("comparison");

    const missingPeriods = generationMetadata.comparison.missing_timestamp_periods;
    for (const resultFinding of analyzed.analysis.findings) {
      expect(`${resultFinding.title} ${resultFinding.summary}`).not.toMatch(/\bmissing data\b|\bdata gap\b/i);
      expect(nearMissingPeriod(resultFinding.first_surfaced_at, missingPeriods)).toBe(false);
      for (const relationship of resultFinding.relationships) {
        expect(relationship.what_changed).not.toMatch(/\bmissing data\b|\bdata gap\b/i);
        expect(nearMissingPeriod(relationship.start_time, missingPeriods)).toBe(false);
      }
    }

    expect(analysisLocked).toBe(true);
    const hiddenEvent = JSON.parse(await readFile(hiddenEventPath, "utf8"));
    hiddenEventWasRead = true;
    expect(hiddenEventWasRead).toBe(true);
    await expect(page.getByRole("heading", { name: "Reveal the known event only now" })).toBeVisible();
    await page.getByLabel("Known event or work-order label").fill(hiddenEvent.event_label);
    await page.getByLabel("Known event timestamp (UTC)").fill(asDateTimeLocal(hiddenEvent.event_timestamp));
    await page.getByLabel("Repair or recovery timestamp (UTC, optional)").fill(asDateTimeLocal(hiddenEvent.repair_timestamp));
    const eventResponsePromise = page.waitForResponse(
      (response) => response.url().includes(`/api/pilot-assessments/${intake.assessment_id}/event`)
        && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Run event backtest" }).click();
    const eventResponse = await eventResponsePromise;
    expect(eventResponse.ok()).toBeTruthy();
    const revealed = await eventResponse.json();
    const backtest = revealed.event_backtest;
    expect(backtest.analysis_was_blinded).toBe(true);
    expect(Date.parse(backtest.event_timestamp)).toBe(Date.parse(hiddenEvent.event_timestamp));
    expect(Date.parse(backtest.repair_timestamp)).toBe(Date.parse(hiddenEvent.repair_timestamp));
    const findingBacktest = backtest.findings.find((item) => item.finding_id === finding.finding_id);
    expect(findingBacktest).toBeTruthy();
    expect(findingBacktest.lead_time_hours).toBe(
      Math.round(
        ((Date.parse(hiddenEvent.event_timestamp) - Date.parse(finding.first_surfaced_at)) / 3_600_000) * 100,
      ) / 100,
    );
    expect(findingBacktest.persisted_through_event).not.toBeNull();
    expect(findingBacktest.disappeared_after_repair).not.toBeNull();
    await expect(page.getByText("Blinded analysis confirmed")).toBeVisible();
    await expect(page.getByText(`${findingBacktest.lead_time_hours.toFixed(2)} hours before event`, { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Why this finding is credible" })).toBeVisible();
    await expect(page.getByText(`Detected ${findingBacktest.lead_time_hours.toFixed(2)} hours before the recorded event`, { exact: true })).toBeVisible();
    await expect(page.getByText("Persisted through the event", { exact: true })).toBeVisible();
    await expect(page.getByText(`Supported by ${finding.evidence_count} changed relationships`, { exact: true })).toBeVisible();
    await expect(page.getByText("Disappeared after repair", { exact: true })).toBeVisible();
    await expect(page.getByText(/Finding disappeared|Finding remained/).first()).toBeVisible();

    const repairTime = Date.parse(hiddenEvent.repair_timestamp);
    const preRepairScores = finding.relationships.flatMap((relationship) => (
      relationship.persistence.windows
        .filter((window) => Date.parse(window.start) < repairTime && window.supports_change)
        .map((window) => Number(window.deviation_score))
    ));
    const postRepairScores = finding.relationships.flatMap((relationship) => (
      relationship.persistence.windows
        .filter((window) => Date.parse(window.start) >= repairTime)
        .map((window) => Number(window.deviation_score))
    ));
    expect(preRepairScores.length).toBeGreaterThan(0);
    expect(postRepairScores.length).toBeGreaterThan(0);
    const preRepairMedian = Number(median(preRepairScores).toFixed(2));
    const postRepairMedian = Number(median(postRepairScores).toFixed(2));
    const reduction = ((preRepairMedian - postRepairMedian) / preRepairMedian) * 100;
    expect(postRepairMedian).toBeLessThan(preRepairMedian);
    await expect(page.getByText(
      `Median behavioral deviation decreased from ${preRepairMedian.toFixed(2)} before repair to ${postRepairMedian.toFixed(2)} after repair.`,
      { exact: true },
    )).toBeVisible();
    await expect(page.getByText(`${reduction.toFixed(2)}% reduction`, { exact: true })).toBeVisible();

    const firstFeedbackNote = "Hydraulic efficiency change is useful and aligns with the repair record.";
    await page.getByLabel("Engineer notes").fill(firstFeedbackNote);
    const firstFeedbackPromise = page.waitForResponse(
      (response) => response.url().includes(`/api/pilot-assessments/${intake.assessment_id}/feedback`)
        && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Append feedback" }).click();
    const firstFeedbackResponse = await firstFeedbackPromise;
    expect(firstFeedbackResponse.status()).toBe(201);
    const firstFeedbackAssessment = await firstFeedbackResponse.json();
    const firstFeedback = firstFeedbackAssessment.feedback_history.at(-1);

    const secondFeedbackNote = "Review valve authority and differential-pressure sensor calibration.";
    await page.getByLabel("Needs investigation").check();
    await page.getByLabel("Engineer notes").fill(secondFeedbackNote);
    const secondFeedbackPromise = page.waitForResponse(
      (response) => response.url().includes(`/api/pilot-assessments/${intake.assessment_id}/feedback`)
        && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Append feedback" }).click();
    const secondFeedbackResponse = await secondFeedbackPromise;
    expect(secondFeedbackResponse.status()).toBe(201);
    const feedbackAssessment = await secondFeedbackResponse.json();
    expect(feedbackAssessment.feedback_history.length).toBe(firstFeedbackAssessment.feedback_history.length + 1);
    expect(feedbackAssessment.feedback_history.at(-2)).toEqual(firstFeedback);
    expect(feedbackAssessment.feedback_history.at(-1).feedback_id).not.toBe(firstFeedback.feedback_id);
    await expect(page.getByText(firstFeedbackNote)).toBeVisible();
    await expect(page.getByText(secondFeedbackNote)).toBeVisible();

    const reportDownloadPromise = page.waitForEvent("download");
    await page.getByRole("link", { name: "Export HTML report" }).click();
    const reportDownload = await reportDownloadPromise;
    await reportDownload.saveAs(reportPath);
    const reportHtml = await readFile(reportPath, "utf8");
    expect(reportHtml).toContain("Neraium Golden Nugget historical assessment");
    expect(reportHtml).toContain(finding.title);
    expect(reportHtml).toContain("The system required a different level of pump demand to produce the hydraulic response learned during the baseline period.");
    expect(reportHtml).toContain(String(findingBacktest.lead_time_hours));
    const reportSections = [
      "Finding",
      "What changed",
      "Detection timeline",
      "Why this finding is credible",
      "Supporting relationship evidence",
      "Before-and-after repair comparison",
      "Data quality notes",
      "Methodology and limitations",
    ];
    const reportSectionIndexes = reportSections.map((title) => reportHtml.indexOf(`<h2>${title}</h2>`));
    expect(reportSectionIndexes.every((index) => index >= 0)).toBe(true);
    expect(reportSectionIndexes).toEqual([...reportSectionIndexes].sort((left, right) => left - right));
    expect(reportHtml).toContain(`Median behavioral deviation decreased from ${preRepairMedian.toFixed(2)} before repair to ${postRepairMedian.toFixed(2)} after repair.`);
    expect(reportHtml).toContain(`${reduction.toFixed(2)}% reduction`);
    expect(reportHtml).toContain("7 duplicate baseline timestamps were excluded");
    expect(reportHtml).toContain("Tower-enable coverage was limited during the comparison period");
    expect(reportHtml).toContain("Neraium identifies persistent changes in learned operating relationships. It does not independently diagnose equipment failure or replace engineering judgment.");
    expect(reportHtml).toContain(firstFeedbackNote);
    expect(reportHtml).toContain(secondFeedbackNote);
    expect(reportHtml).toContain(firstRelationship.exact_records.sha256);

    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByText(firstFeedbackNote)).toBeVisible();
    await expect(page.getByText(secondFeedbackNote)).toBeVisible();

    const runSummary = {
      assessment_id: intake.assessment_id,
      baseline_csv: baselinePath,
      comparison_csv: comparisonPath,
      hidden_event_fixture: hiddenEventPath,
      exported_report: reportPath,
      finding_title: finding.title,
      first_detection_time: finding.first_surfaced_at,
      hidden_event_time: backtest.event_timestamp,
      lead_time_hours: findingBacktest.lead_time_hours,
      supporting_evidence_count: finding.evidence_count,
      baseline_quality_result: analyzed.quality_gate.decision,
      baseline_quality_summary: analyzed.quality_gate.summary,
      baseline_quality_warnings: analyzed.quality_gate.warnings,
      operating_modes: analyzed.operating_modes,
      persisted_through_event: findingBacktest.persisted_through_event,
      disappeared_after_repair: findingBacktest.disappeared_after_repair,
      post_repair_median_deviation_score: median(postRepairScores),
      pre_repair_supported_median_deviation_score: median(preRepairScores),
      feedback_record_count: feedbackAssessment.feedback_history.length,
      evidence_download: evidencePath,
    };
    await writeFile(runSummaryPath, `${JSON.stringify(runSummary, null, 2)}\n`, "utf8");
    console.log(`NERAIUM_RESORT_RESULT ${JSON.stringify(runSummary)}`);
  });
});
