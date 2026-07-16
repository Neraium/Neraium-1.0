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
  await expect(page.getByRole("main", { name: "Neraium operational workspace" })).toBeVisible();
}

async function startCommandCenterUpload(page, { name, csv }) {
  await openCommandCenter(page);
  const uploadAcceptedPromise = page.waitForResponse(
    (response) => response.url().includes("/api/data/upload") && response.request().method() === "POST",
    { timeout: 30000 },
  );
  await page.getByTestId("overview-csv-upload-input").setInputFiles({
    name,
    mimeType: "text/csv",
    buffer: Buffer.from(csv, "utf8"),
  });
  await expect(page.getByTestId("upload-workspace")).toBeVisible({ timeout: 30000 });
  const uploadAccepted = await uploadAcceptedPromise;
  expect(uploadAccepted.ok()).toBeTruthy();
}

test.describe("Setup + Upload regression", () => {
  test("opens command-center upload entry without the setup wizard", async ({ page }) => {
    await openCommandCenter(page);
    await expect(page.getByTestId("onboarding-root")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Analyze Historical Telemetry" })).toBeVisible();
    await expect(page.getByTestId("overview-csv-upload-input")).toBeAttached();
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
    await expect(page.getByRole("main", { name: "Neraium operational workspace" })).toBeVisible({ timeout: 120000 });
    await expect(page.getByRole("region", { name: "Operational Status" })).not.toContainText("Awaiting Initial Baseline");
  });
});
