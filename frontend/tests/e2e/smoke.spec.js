import { expect, test } from "./fixtures.js";

test.describe("Neraium frontend smoke", () => {
  test("loads command center workspace", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await expect(page.getByRole("main", { name: "Neraium platform workspace" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Operational Status" })).toBeVisible();
    await expect(page.getByText("Not established", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Import dataset" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Connect telemetry" })).toBeVisible();
  });

  test("empty workspace shows no imported dataset metadata", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await page.getByRole("button", { name: /Datasets & Connectors/ }).click();
    const dataStatus = page.getByRole("region", { name: "Data Source Status" });
    await expect(dataStatus).toBeVisible();
    await expect(dataStatus.getByText("Not imported", { exact: true })).toBeVisible();
    await expect(dataStatus.getByText("0", { exact: true })).toBeVisible();
    await expect(dataStatus.getByText("None", { exact: true })).toBeVisible();
    await expect(dataStatus).not.toContainText("4032");
  });

  test("mobile loads command center workspace", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");

    await expect(page.getByRole("main", { name: "Neraium platform workspace" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Command Center Overview" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Operational Status" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Import dataset" })).toBeVisible();
  });
});
