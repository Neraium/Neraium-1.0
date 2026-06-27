import { expect, test } from "@playwright/test";

async function openDataConnections(page) {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "neraium.local_auth.users",
      JSON.stringify([
        {
          email: "operator@facility.com",
          name: "Operator",
          created_at: "2026-05-21T00:00:00.000Z",
        },
      ]),
    );
    window.localStorage.setItem("neraium.local_auth.session", "operator@facility.com");
  });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  if (!(await page.getByTestId("upload-workspace").isVisible().catch(() => false))) {
    await page.getByRole("button", { name: /Upload CSV|Analyze System|Upload Data/i }).click();
  }
  await expect(page.getByTestId("upload-workspace")).toBeVisible();
  await expect(page.getByTestId("csv-upload-input")).toBeAttached();
  await expect(page.getByTestId("process-upload-button")).toBeVisible();
}

test.describe("Setup + Upload regression", () => {
  test("opens upload surface without the setup wizard", async ({ page }) => {
    await openDataConnections(page);
    await expect(page.getByTestId("onboarding-root")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Analyze System" })).toBeVisible();
  });

  test("enables upload processing after file selection", async ({ page }) => {
    await openDataConnections(page);
    const processButton = page.getByTestId("process-upload-button");
    await expect(processButton).toBeDisabled();
    await expect(page.getByTestId("onboarding-demo-csv-option")).toBeVisible();

    const input = page.locator("input#csv-upload");
    await input.setInputFiles({
      name: "e2e-sample.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("timestamp,temperature,humidity\n2026-05-01T08:00:00Z,75.2,58\n"),
    });

    await expect(page.getByText("e2e-sample.csv")).toBeVisible();
    await expect(processButton).toBeEnabled();
  });

  test("large CSV upload moves progress and completes analysis", async ({ page }) => {
    await openDataConnections(page);
    const processButton = page.getByTestId("process-upload-button");
    const row = "2026-05-01T08:00:00Z,Chilled Water Plant,42.1,58.2,71.4,1.2\n";
    const targetBytes = 16 * 1024 * 1024;
    const repeats = Math.ceil(targetBytes / row.length);
    const csv = `timestamp,room,supply_temp,return_temp,pump_speed,flow_rate\n${row.repeat(repeats)}`;

    await page.locator("input#csv-upload").setInputFiles({
      name: "chilled_water_system_data.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(csv),
    });

    await expect(page.getByText("chilled_water_system_data.csv")).toBeVisible();
    await expect(processButton).toBeEnabled();
    await processButton.click();
    await expect(page.getByRole("progressbar", { name: /Telemetry transfer/i })).toHaveAttribute("aria-valuenow", /[1-9][0-9]*|100/, { timeout: 30000 });
    await expect(page.getByText(/Analysis ready|Telemetry processing complete/i)).toBeVisible({ timeout: 90000 });
  });
});
