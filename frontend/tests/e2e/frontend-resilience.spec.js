import path from "node:path";

import { expect, test } from "./fixtures.js";

const e2eDatabaseURL = `sqlite:///${path.resolve(process.cwd(), "../.playwright-runtime/e2e-telemetry.sqlite").replaceAll("\\", "/")}`;

test.describe("Frontend production resilience", () => {
  test("production command center has no console errors or unhandled rejections", async ({ page }) => {
    const browserErrors = [];
    page.on("console", (message) => {
      if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
    });
    page.on("pageerror", (error) => browserErrors.push(`pageerror: ${error.message}`));

    await page.goto("/workspace", { waitUntil: "networkidle" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    await expect(page.getByRole("heading", { name: "Operational Status" })).toBeVisible();
    expect(browserErrors, browserErrors.join("\n")).toEqual([]);
  });

  test("delayed insights load, failed request, and refresh recovery never leave a stuck shell", async ({ page }) => {
    let releaseInitialRequest;
    const initialRequestGate = new Promise((resolve) => { releaseInitialRequest = resolve; });
    const evidencePattern = "**/api/evidence/runs?**";

    await page.route(evidencePattern, async (route) => {
      await initialRequestGate;
      await route.continue();
    });
    await page.goto("/workspace/insights", { waitUntil: "domcontentloaded" });
    await expect(page.getByText("Loading insights and supporting evidence...")).toBeVisible();
    releaseInitialRequest();
    await expect(page.getByRole("heading", { name: "Operational Insights" })).toBeVisible();
    await page.unroute(evidencePattern);

    await page.route(evidencePattern, (route) => route.abort("connectionfailed"));
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByText("Insights Unavailable")).toBeVisible();
    await expect(page.getByText("The analysis service could not be reached. Check service health and retry.")).toBeVisible();
    await page.unroute(evidencePattern);

    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Operational Insights" })).toBeVisible();
    await expect(page.getByText("Filter and search insights")).toBeVisible();
  });

  test("recorded insight history remains searchable and filterable without a current finding", async ({ page }) => {
    const runs = [
      {
        run_id: "historical-run-1",
        source_type: "csv_upload",
        source_name: "historical.csv",
        status: "completed",
        created_at: "2026-06-16T00:00:00Z",
        observation_type: "trajectory_drift",
        observation_status: "open",
        variables: ["temperature", "humidity"],
        drift_metrics: { baseline_distance: 0.7 },
        evidence_summary: ["System behavior changed."],
      },
      {
        run_id: "historical-run-2",
        source_type: "csv_upload",
        source_name: "relationships.csv",
        status: "completed",
        created_at: "2026-06-15T00:00:00Z",
        observation_type: "coupling_change",
        observation_status: "resolved",
        variables: ["flow", "pressure"],
        drift_metrics: { baseline_distance: 0.4 },
        evidence_summary: ["Flow and pressure changed together."],
      },
    ];
    const evidencePattern = "**/api/evidence/runs?**";
    await page.route(evidencePattern, (route) => {
      const origin = route.request().headers().origin ?? "*";
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "access-control-allow-origin": origin,
          "access-control-allow-credentials": "true",
        },
        body: JSON.stringify({ runs, has_more: false, next_offset: null }),
      });
    });

    await page.goto("/workspace/insights", { waitUntil: "domcontentloaded" });
    const firstRun = page.getByRole("button", { name: "Review Behavior Change Continuing from historical.csv" });
    const secondRun = page.getByRole("button", { name: "Review System Behavior Shift from relationships.csv" });
    await expect(firstRun).toBeVisible();
    await expect(secondRun).toBeVisible();
    await expect(firstRun).toHaveAttribute("aria-pressed", "true");

    await page.getByText("Filter and search insights").click();
    await page.getByLabel("Search insights").fill("relationships.csv");
    await expect(firstRun).toHaveCount(0);
    await expect(secondRun).toBeVisible();

    await page.getByLabel("Search insights").fill("");
    await page.getByLabel("Status").selectOption("resolved");
    await expect(firstRun).toHaveCount(0);
    await expect(secondRun).toBeVisible();
    await page.unroute(evidencePattern);
  });
  test("connector abort is actionable, retry succeeds, and a pending action cannot duplicate", async ({ page }) => {
    let requestCount = 0;
    let releaseRetry;
    const retryGate = new Promise((resolve) => { releaseRetry = resolve; });
    const connectorPattern = "**/api/connectors/database/test";

    await page.goto("/workspace/data-sources", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Telemetry Connector Setup" })).toBeVisible();
    await page.getByLabel("Connector type").selectOption("database");
    await page.getByLabel("Database URL").fill(e2eDatabaseURL);

    await page.route(connectorPattern, async (route) => {
      requestCount += 1;
      if (requestCount === 1) {
        await route.abort("connectionfailed");
        return;
      }
      await retryGate;
      await route.continue();
    });

    await page.getByRole("button", { name: "Test connection" }).click();
    await expect(page.getByRole("alert")).toContainText("could not be reached");

    await page.getByRole("button", { name: "Test connection" }).click();
    const pendingButton = page.getByRole("button", { name: "Testing..." });
    await expect(pendingButton).toBeDisabled();
    await expect.poll(() => requestCount).toBe(2);
    await pendingButton.evaluate((button) => button.click());
    expect(requestCount).toBe(2);

    releaseRetry();
    await expect(page.getByRole("status")).toContainText("No records were saved");
    expect(requestCount).toBe(2);
    await page.unroute(connectorPattern);
  });
});