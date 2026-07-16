import { expect, test } from "@playwright/test";

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
  await expect(page.getByText(name, { exact: true })).toBeVisible();
  const uploadAccepted = await uploadAcceptedPromise;
  expect(uploadAccepted.ok()).toBeTruthy();
}

test.describe("Setup + Upload regression", () => {
  test("opens command-center upload entry without the setup wizard", async ({ page }) => {
    await openCommandCenter(page);
    await expect(page.getByTestId("onboarding-root")).toHaveCount(0);
    const commandCenterNav = page
      .getByRole("navigation", { name: "Primary workflow navigation" })
      .getByRole("button", { name: /^Command Center/ });
    await expect(commandCenterNav).toBeVisible();
    await expect(commandCenterNav).toHaveAttribute("aria-current", "page");
    await expect(page.getByTestId("overview-csv-upload-input")).toBeAttached();
  });

  test("command-center file selection opens the upload workspace", async ({ page }) => {
    await startCommandCenterUpload(page, {
      name: "e2e-sample.csv",
      csv: "timestamp,temperature,humidity\n2026-05-01T08:00:00Z,75.2,58\n",
    });
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

    const baselineNetwork = page.getByTestId("baseline-network-progress");
    await expect(baselineNetwork).toBeVisible({ timeout: 30000 });
    const accessibleProgress = baselineNetwork.getByRole("progressbar", { name: /Analysis \d+% complete/ });
    await expect(accessibleProgress).toHaveAttribute("aria-valuenow", /\d+/);
    await baselineNetwork.scrollIntoViewIfNeeded();
    const isContainedInViewport = await baselineNetwork.evaluate((element) => {
      const bounds = element.getBoundingClientRect();
      return bounds.left >= -1
        && bounds.top >= -1
        && bounds.right <= window.innerWidth + 1
        && bounds.bottom <= window.innerHeight + 1;
    });
    expect(isContainedInViewport).toBeTruthy();

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(baselineNetwork).toBeVisible();
    const isHorizontallyContainedInViewport = await baselineNetwork.evaluate((element) => {
      const bounds = element.getBoundingClientRect();
      return bounds.left >= -1 && bounds.right <= window.innerWidth + 1;
    });
    expect(isHorizontallyContainedInViewport).toBeTruthy();
    const hasNoHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
    );
    expect(hasNoHorizontalOverflow).toBeTruthy();

    await expect(page.getByRole("heading", { name: /Analysis Complete|Behavioral Baseline Established/ })).toBeVisible({ timeout: 120000 });
  });
});
