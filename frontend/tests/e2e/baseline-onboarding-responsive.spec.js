import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures.js";

const MOBILE_VIEWPORTS = [
  { name: "iPhone Safari width", width: 390, height: 844 },
  { name: "narrow Android width", width: 320, height: 720 },
  { name: "mobile landscape", width: 844, height: 390 },
];

async function openBaselineImport(page, viewport = { width: 1440, height: 900 }) {
  await page.setViewportSize(viewport);
  await page.goto("/workspace/data-sources", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  await expect(page.getByRole("heading", { name: "Establish Initial Baseline", level: 2 })).toBeVisible();
}

async function chooseSampleDataset(page) {
  await page.getByTestId("csv-upload-input").setInputFiles({
    name: "central-plant-history.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("timestamp,flow,pressure\n2026-07-01T00:00:00Z,10,12\n", "utf8"),
  });
}

test.describe("Initial baseline learning experience", () => {
  test("makes the compact upload workflow and primary action immediately clear", async ({ page }) => {
    await openBaselineImport(page);

    await expect(page.getByText("Upload representative historical operating data so Neraium can learn how the system normally behaves.")).toBeVisible();
    await expect(page.getByText("SOURCE OPERATING HISTORY")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Upload historical data", level: 3 })).toBeVisible();
    await expect(page.getByText("CSV, SCADA export, or historian export")).toBeVisible();
    await expect(page.getByText("This dataset becomes Neraium's first learned operating model.")).toHaveCount(0);
    await expect(page.getByText(/discovers persistent relationships between signals/i)).toHaveCount(0);
    await expect(page.getByText(/normal only evolves when new operating behavior/i)).toHaveCount(0);

    const steps = page.getByRole("list", { name: "How Neraium establishes its initial baseline" }).getByRole("listitem");
    await expect(steps).toHaveCount(5);
    await expect(steps).toHaveText([
      "1Upload Data",
      "2Validate Signals",
      "3Learn Relationships",
      "4Establish Baseline",
      "5Begin Learning",
    ]);

    const choose = page.getByRole("button", { name: /choose historical dataset/i });
    const continueAction = page.getByRole("button", { name: "Continue" });
    await expect(choose).toBeVisible();
    await expect(continueAction).toBeVisible();
    await expect(page.getByText("Supported data sources")).toHaveCount(0);
    await expect(page.getByText("Choose a telemetry file.")).toHaveCount(0);
    await continueAction.click();
    await expect(page.locator(".upload-analysis-card--baseline .upload-error-message")).toHaveText("Choose a telemetry file.");
    await expect(page.getByText("Compare", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Evidence", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Findings", { exact: true })).toHaveCount(0);

    await chooseSampleDataset(page);
    const replace = page.getByRole("button", { name: "Replace file" });
    await expect(continueAction).toBeVisible();
    await expect(continueAction).toBeEnabled();
    await expect(replace).toBeVisible();
    await expect(page.getByText("central-plant-history.csv")).toBeVisible();
    await expect(page.getByRole("button", { name: "Analyze New Data" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Extend Baseline" })).toHaveCount(0);

    const hierarchy = await page.evaluate(() => {
      const primary = document.querySelector(".upload-baseline-card__primary");
      const secondary = document.querySelector(".baseline-file-replace");
      const primaryBox = primary.getBoundingClientRect();
      const secondaryBox = secondary.getBoundingClientRect();
      return {
        primaryWidth: primaryBox.width,
        secondaryWidth: secondaryBox.width,
        primaryHeight: primaryBox.height,
      };
    });
    expect(hierarchy.primaryWidth).toBeGreaterThan(hierarchy.secondaryWidth);
    expect(hierarchy.primaryHeight).toBeGreaterThanOrEqual(44);
  });

  test("has no horizontal overflow and keeps touch controls usable across mobile sizes", async ({ page }) => {
    for (const viewport of MOBILE_VIEWPORTS) {
      await openBaselineImport(page, viewport);
      await chooseSampleDataset(page);

      const layout = await page.evaluate(() => {
        const controls = Array.from(document.querySelectorAll(".upload-analysis-card--baseline button, .upload-analysis-card--baseline summary")).map((node) => {
          const box = node.getBoundingClientRect();
          return {
            label: node.textContent.trim(),
            left: box.left,
            right: box.right,
            width: box.width,
            height: box.height,
          };
        });
        return {
          viewportWidth: window.innerWidth,
          rootWidth: document.documentElement.scrollWidth,
          bodyWidth: document.body.scrollWidth,
          controls,
        };
      });

      expect(layout.rootWidth, viewport.name).toBeLessThanOrEqual(layout.viewportWidth + 1);
      expect(layout.bodyWidth, viewport.name).toBeLessThanOrEqual(layout.viewportWidth + 1);
      for (const control of layout.controls) {
        expect(control.left, `${viewport.name}: ${control.label} left`).toBeGreaterThanOrEqual(0);
        expect(control.right, `${viewport.name}: ${control.label} right`).toBeLessThanOrEqual(viewport.width + 1);
        expect(control.width, `${viewport.name}: ${control.label} width`).toBeGreaterThanOrEqual(24);
        expect(control.height, `${viewport.name}: ${control.label} height`).toBeGreaterThanOrEqual(34);
        expect(control.height, `${viewport.name}: ${control.label} height`).toBeLessThanOrEqual(60);
      }
    }
  });

  test("keeps a stored mobile transfer complete when dataset creation fails", async ({ page }) => {
    let objectPuts = 0;
    let retryCalls = 0;
    const failure = {
      job_id: "mobile-stored-session",
      upload_session_id: "mobile-stored-session",
      status: "FAILED",
      processing_state: "failed",
      error_type: "upload_enqueue_failed",
      error_code: "dataset_record_creation_failed",
      message: "The file was transferred successfully, but Neraium could not begin processing it.",
      failed_stage: "dataset_creation",
      retryable: true,
      transfer_succeeded: true,
      file_stored: true,
      retry_url: "/api/data/upload/mobile-stored-session/retry",
    };

    await page.route("**/api/data/upload-session", (route) => route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        upload_session_id: "mobile-stored-session",
        upload_url: "https://upload.example.test/mobile-stored-session",
        upload_headers: { "Content-Type": "text/csv" },
      }),
    }));
    await page.route("https://upload.example.test/mobile-stored-session", (route) => {
      objectPuts += 1;
      return route.fulfill({ status: 200, headers: { etag: '"mobile-etag"' }, body: "" });
    });
    await page.route("**/api/data/upload-session/mobile-stored-session/complete", (route) => route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify(failure),
    }));
    await page.route("**/api/data/upload/mobile-stored-session/retry", (route) => {
      retryCalls += 1;
      return route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify(failure),
      });
    });

    await openBaselineImport(page, { width: 390, height: 844 });
    await chooseSampleDataset(page);
    await page.getByRole("button", { name: "Continue" }).click();

    await expect(page.getByRole("heading", { name: "Dataset import failed" })).toBeVisible();
    await expect(page.getByText("The file was transferred successfully, but Neraium could not begin processing it.", { exact: true }).first()).toBeVisible();
    const workflowStatus = page.getByRole("list", { name: "Import workflow status" });
    await expect(workflowStatus.getByRole("listitem")).toHaveText([
      "!Import DatasetFailed",
      "–Validate SignalsNot started",
      "–Learn RelationshipsNot started",
      "–Establish BaselineNot started",
      "–Begin LearningNot started",
    ]);
    await expect(page.getByRole("button", { name: "Retry Import" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Choose Another File" })).toBeVisible();
    expect(objectPuts).toBe(1);

    await page.getByRole("button", { name: "Retry Import" }).click();
    await expect.poll(() => retryCalls).toBe(1);
    await expect(page.getByRole("heading", { name: "Dataset import failed" })).toBeVisible();
    expect(objectPuts).toBe(1);
  });

  test("supports keyboard file selection and passes the changed-component accessibility audit", async ({ page }) => {
    await openBaselineImport(page);
    const choose = page.getByRole("button", { name: /choose historical dataset/i });
    await choose.focus();
    await expect(choose).toBeFocused();
    const chooserPromise = page.waitForEvent("filechooser");
    await page.keyboard.press("Enter");
    const chooser = await chooserPromise;
    await chooser.setFiles({
      name: "keyboard-history.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("timestamp,value\n2026-07-01T00:00:00Z,1\n", "utf8"),
    });
    await expect(page.getByRole("button", { name: "Continue" })).toBeVisible();

    const results = await new AxeBuilder({ page })
      .include(".upload-ops-panel--command")
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    const serious = results.violations.filter((item) => ["serious", "critical"].includes(item.impact));
    expect(serious.map((item) => ({ id: item.id, targets: item.nodes.map((node) => node.target) }))).toEqual([]);
  });
});
