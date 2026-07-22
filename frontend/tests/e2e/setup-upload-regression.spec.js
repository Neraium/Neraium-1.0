import { expect, test } from "./fixtures.js";

async function openCommandCenter(page) {
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
  await expect(page.getByRole("main", { name: "Neraium platform workspace" })).toBeVisible();
}

async function startCommandCenterUpload(page, { name, csv }) {
  await openCommandCenter(page);
  await page.getByRole("button", { name: "Data Connections" }).click();
  await expect(page.getByRole("heading", { name: "Import and Analyze Dataset", level: 2 })).toBeVisible();
  const uploadAcceptedPromise = page.waitForResponse(
    (response) => response.url().includes("/api/data/upload") && response.request().method() === "POST",
    { timeout: 30000 },
  );
  await page.getByTestId("csv-upload-input").setInputFiles({
    name,
    mimeType: "text/csv",
    buffer: Buffer.from(csv, "utf8"),
  });
  await page.getByRole("button", { name: "Analyze Dataset" }).click();
  await expect(page.getByTestId("upload-workspace")).toBeVisible({ timeout: 30000 });
  const uploadAccepted = await uploadAcceptedPromise;
  expect(uploadAccepted.ok()).toBeTruthy();
}

test.describe("Setup + Upload regression", () => {
  test("opens command-center upload entry without the setup wizard", async ({ page }) => {
    await openCommandCenter(page);
    await expect(page.getByTestId("onboarding-root")).toHaveCount(0);
    await page.getByRole("button", { name: "Data Connections" }).click();
  await expect(page.getByRole("heading", { name: "Import and Analyze Dataset", level: 2 })).toBeVisible();
    await expect(page.getByTestId("csv-upload-input")).toBeAttached();
  });

  test("command-center file selection opens the upload workspace", async ({ page }) => {
    await startCommandCenterUpload(page, {
      name: "e2e-sample.csv",
      csv: "timestamp,temperature,humidity\n2026-05-01T08:00:00Z,75.2,58\n",
    });

    await expect(page.getByTestId("upload-workspace")).toBeVisible();
    await expect(page.locator("body")).not.toContainText("We hit a workspace error");
  });

  test("large CSV upload moves progress and completes analysis", async ({ page }) => {
    const row = "2026-05-01T08:00:00Z,Chilled Water Plant,42.1,58.2,71.4,1.2\n";
    const targetBytes = 16 * 1024 * 1024;
    const repeats = Math.ceil(targetBytes / row.length);
    const csv = `timestamp,room,supply_temp,return_temp,pump_speed,flow_rate\n${row.repeat(repeats)}`;

    await startCommandCenterUpload(page, {
      name: "chilled_water_system_data.csv",
      csv,
    });

    await expect(page.getByRole("progressbar", { name: /Telemetry transfer|Analysis/i })).toHaveAttribute("aria-valuenow", /[1-9][0-9]*|100/, { timeout: 30000 });
    await expect(page.getByRole("region", { name: "Analysis complete" })).toBeVisible({ timeout: 120000 });
    const viewResults = page.getByRole("button", { name: /View Results|Open Portfolio/i });
    if (await viewResults.count()) await viewResults.first().click();
    await expect(page.getByTestId("engineering-reasoning-platform")).toBeVisible({ timeout: 30000 });
  });
});
