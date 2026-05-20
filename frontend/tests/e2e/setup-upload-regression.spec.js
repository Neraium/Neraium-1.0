import { expect, test } from "@playwright/test";

async function openDataConnections(page) {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  await page.getByRole("button", { name: "Open Gate settings" }).click();
  await page.getByRole("button", { name: /Setup & data connections|Data connections/i }).click();
  await expect(page.getByRole("tab", { name: /Setup|Live Link/i })).toBeVisible();
}

test.describe("Setup + Upload regression", () => {
  test("progresses through setup without brittle copy checks", async ({ page }) => {
    await openDataConnections(page);

    await expect(page.getByTestId("onboarding-root")).toBeVisible();
    const stepTitle = page.getByTestId("onboarding-step-title");
    const nextButton = page.getByTestId("onboarding-next-button");

    await expect(stepTitle).toContainText("Step 1 of");
    await expect(stepTitle).toContainText("Historian / BMS / SCADA");

    await nextButton.click();
    await expect(stepTitle).toContainText("Read-only Ingestion");

    await nextButton.click();
    await expect(page.getByTestId("onboarding-data-source-step")).toBeVisible();
    await expect(stepTitle).toContainText("Connection Method");

    await nextButton.click();
    await expect(page.getByTestId("signal-mapping-step")).toBeVisible();
    await expect(stepTitle).toContainText("Signal Mapping");

    await nextButton.click();
    await expect(stepTitle).toContainText("Connection Test");
    await page.getByRole("button", { name: "Run Test" }).click();
    const continueToBaselineButton = page.getByRole("button", { name: "Continue to Baseline Builder" });
    await expect(continueToBaselineButton).toBeEnabled();
    await continueToBaselineButton.click();

    await expect(stepTitle).toContainText("Baseline Builder");
    await expect(nextButton).toBeDisabled();
  });

  test("enables upload processing after file selection", async ({ page }) => {
    await openDataConnections(page);
    await page.getByRole("tab", { name: "Upload Data" }).click();

    const processButton = page.getByRole("button", { name: /Process CSV/i });
    await expect(processButton).toBeDisabled();
    await expect(page.getByTestId("onboarding-demo-csv-option")).toBeVisible();

    const input = page.locator("input#csv-upload");
    await input.setInputFiles({
      name: "e2e-sample.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("timestamp,temperature,humidity\n2026-05-01T08:00:00Z,75.2,58\n"),
    });

    await expect(page.getByText("Telemetry export validated.")).toBeVisible();
    await expect(processButton).toBeEnabled();
  });
});
