import { expect, test } from "@playwright/test";

async function openDataConnections(page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Open Gate settings" }).click();
  await page.getByRole("button", { name: /Data connections/i }).click();
  await expect(page.getByRole("tab", { name: "Live Link" })).toBeVisible();
}

test.describe("Setup + Upload regression", () => {
  test("progresses through setup steps 1 to 7", async ({ page }) => {
    await openDataConnections(page);

    await expect(page.getByText("Step 1 of 7: 1. Historian / BMS / SCADA")).toBeVisible();
    const nextButton = page.getByRole("button", { name: "Next" });

    await nextButton.click();
    await expect(page.getByText("Step 2 of 7: 2. Read-only Ingestion")).toBeVisible();
    await nextButton.click();
    await expect(page.getByText("Step 3 of 7: 3. Neraium Intake Connector")).toBeVisible();
    await nextButton.click();
    await expect(page.getByText("Step 4 of 7: 4. Signal Mapping")).toBeVisible();
    await nextButton.click();
    await expect(page.getByText("Step 5 of 7: 5. Baseline Builder")).toBeVisible();
    await nextButton.click();
    await expect(page.getByText("Step 6 of 7: 6. Live Structural Analysis")).toBeVisible();
    await nextButton.click();
    await expect(page.getByText("Step 7 of 7: 7. Operator UI / Reports")).toBeVisible();
    await expect(nextButton).toBeDisabled();
  });

  test("enables upload processing after file selection", async ({ page }) => {
    await openDataConnections(page);
    await page.getByRole("tab", { name: "Upload Data" }).click();

    const processButton = page.getByRole("button", { name: /Process CSV/i });
    await expect(processButton).toBeDisabled();

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
