import { expect, test } from "@playwright/test";

const emptyLatestUpload = {
  session_state: "empty",
  upload_session_id: null,
  job_id: null,
  run_id: null,
  upload_id: null,
  current_upload: { status: "empty", job_id: null, result: null },
  latest_result: null,
  snapshot: {
    status: "empty",
    source: "none",
    message: "No telemetry data.",
    last_filename: null,
    rows_processed: 0,
    columns_detected: 0,
    state_available: false,
    latest_result: null,
  },
};

const persistedLatestUpload = {
  session_state: "restored",
  upload_session_id: "restored-job-1",
  job_id: "restored-job-1",
  run_id: "restored-job-1",
  upload_id: "restored-job-1",
  current_upload: {
    status: "complete",
    job_id: "restored-job-1",
    result: {
      job_id: "restored-job-1",
      filename: "restored-workspace.csv",
      row_count: 12,
      column_count: 4,
      sii_completed: true,
      sii_reliable_enough_to_show: true,
      observation_type: "baseline_shift",
      drift_status: "info",
      processing_trace: { sii_completed: true },
      engine_result: { overall_result: "stable" },
      room_summary: { room_count: 1, rooms: [{ room: "Uploaded telemetry", row_count: 12 }] },
      sii_intelligence: { facility_state: "Monitoring", last_updated: "2026-06-20T00:00:00Z" },
      replay_timeline: { timeline: [{ timestamp: "2026-06-20T00:00:00Z" }] },
      completed_at: "2026-06-20T00:00:00Z",
      last_processed_at: "2026-06-20T00:00:00Z",
    },
  },
  latest_result: null,
  snapshot: {
    status: "complete",
    session_state: "restored",
    current_upload: { job_id: "restored-job-1" },
    last_filename: "restored-workspace.csv",
    rows_processed: 12,
    columns_detected: 4,
    state_available: true,
    sii_completed: true,
    last_processed_at: "2026-06-20T00:00:00Z",
  },
};

async function clearBrowserStorage(page) {
  await page.context().clearCookies();
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.evaluate(async () => {
    localStorage.clear();
    sessionStorage.clear();
    if (indexedDB?.databases) {
      const databases = await indexedDB.databases();
      await Promise.all(databases.map((db) => db?.name ? new Promise((resolve) => {
        const request = indexedDB.deleteDatabase(db.name);
        request.onsuccess = request.onerror = request.onblocked = () => resolve();
      }) : Promise.resolve()));
    }
  });
}

async function stubLatestUpload(page) {
  await page.route("**/api/data/latest-upload**", async (route) => {
    const url = new URL(route.request().url());
    const includePersisted = url.searchParams.get("include_persisted") === "1";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(includePersisted ? persistedLatestUpload : emptyLatestUpload),
    });
  });
}

async function stubResetEndpoints(page) {
  await page.route("**/api/data/reset", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, status: "reset", message: "Workspace reset.", session: emptyLatestUpload }),
    });
  });
  await page.route("**/api/data-connections/reset-all", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, message: "Data connections reset." }),
    });
  });
}

async function openUploadWorkspace(page) {
  await page.getByTestId("workspace-menu-button").click();
  await page.getByTestId("upload-workspace-entry").click();
  await expect(page.getByTestId("upload-workspace")).toBeVisible();
}

test.describe("focused session state QA", () => {
  test("fresh visitor does not render stale analysis controls or metrics", async ({ page }) => {
    await stubLatestUpload(page);
    await clearBrowserStorage(page);
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await expect(page.getByRole("button", { name: "Upload Data" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Review Findings" })).toHaveCount(0);
    await expect(page.getByText("Review Evidence")).toHaveCount(0);
    await expect(page.getByText("restored-workspace.csv")).toHaveCount(0);
    await expect(page.getByText("Evidence confidence")).toHaveCount(0);
    await expect(page.getByText("Operating pattern")).toHaveCount(0);
    await expect(page.getByText("Persistence")).toHaveCount(0);
    await expect(page.getByText("Active observations")).toHaveCount(0);

    await openUploadWorkspace(page);
    await expect(page.getByText("Awaiting file selection").first()).toBeVisible();
    await expect(page.getByText("restored-workspace.csv")).toHaveCount(0);
    await expect(page.getByTestId("process-upload-button")).toBeDisabled();
  });

  test("selected file stays local until upload starts and mobile upload panel has no horizontal overflow", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await stubLatestUpload(page);
    await clearBrowserStorage(page);
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    await openUploadWorkspace(page);

    await page.getByTestId("csv-upload-input").setInputFiles({
      name: "selected-only.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("timestamp,temp\n2026-06-20T00:00:00Z,72\n"),
    });

    await expect(page.getByText("selected-only.csv")).toBeVisible();
    await expect(page.getByText("restored-workspace.csv")).toHaveCount(0);
    await expect(page.getByText(/Processing queued|Uploading telemetry batch|Telemetry batch processing/i)).toHaveCount(0);
    await expect(page.getByTestId("process-upload-button")).toBeEnabled();

    const metrics = await page.evaluate(() => ({
      viewportWidth: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
    }));
    expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.viewportWidth);
    expect(metrics.bodyScrollWidth).toBeLessThanOrEqual(metrics.viewportWidth);
  });


  test("reset returns empty state from empty, selected file, and loaded latest workspace", async ({ page }) => {
    await stubLatestUpload(page);
    await stubResetEndpoints(page);
    await clearBrowserStorage(page);
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    await openUploadWorkspace(page);
    await page.locator("summary", { hasText: "Workspace options" }).click();

    await page.getByRole("button", { name: "Reset Workspace" }).click();
    await expect(page.getByText("Workspace reset.")).toBeVisible();
    await expect(page.getByText("Awaiting file selection").first()).toBeVisible();

    await page.getByTestId("csv-upload-input").setInputFiles({
      name: "reset-selected.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("timestamp,temp\n2026-06-20T00:00:00Z,72\n"),
    });
    await expect(page.getByText("reset-selected.csv")).toBeVisible();
    await page.getByRole("button", { name: "Reset Workspace" }).click();
    await expect(page.getByText("reset-selected.csv")).toHaveCount(0);
    await expect(page.getByTestId("process-upload-button")).toBeDisabled();

    await page.getByRole("button", { name: "Load Latest Workspace" }).click();
    await expect(page.getByText("restored-workspace.csv").first()).toBeVisible();
    await page.getByRole("button", { name: "Reset Workspace" }).click();
    await expect(page.getByText("restored-workspace.csv")).toHaveCount(0);
    await expect(page.getByText("Awaiting file selection").first()).toBeVisible();
  });

  test("load latest workspace is explicit and reports success", async ({ page }) => {
    await stubLatestUpload(page);
    await clearBrowserStorage(page);
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await expect(page.getByText("restored-workspace.csv")).toHaveCount(0);
    await openUploadWorkspace(page);
    await page.locator("summary", { hasText: "Workspace options" }).click();
    await page.getByRole("button", { name: "Load Latest Workspace" }).click();

    await expect(page.getByText("Latest workspace loaded.")).toBeVisible();
    await expect(page.getByText("restored-workspace.csv").first()).toBeVisible();
  });
});
