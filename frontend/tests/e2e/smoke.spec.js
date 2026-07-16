import { expect, test } from "./fixtures.js";

test.describe("Neraium frontend smoke", () => {
  test("loads command center workspace", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await expect(page.getByRole("main", { name: "Neraium platform workspace" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Operational Status" })).toBeVisible();
    await expect(page.getByText("Baseline Needed", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Import and Analyze Dataset" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Connect Live Telemetry" })).toBeVisible();
  });

  test("mobile loads command center workspace", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await expect(page.getByRole("main", { name: "Neraium platform workspace" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Command Center Overview" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Operational Status" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Import and Analyze Dataset" })).toBeVisible();
  });
});
