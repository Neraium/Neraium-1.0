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
  await page.getByRole("button", { name: "Open Gate settings" }).click();
  await page.getByRole("button", { name: /Setup & data connections|Data connections/i }).click();
  await expect(page.getByRole("tab", { name: /^Upload$/i })).toBeVisible();
}

test.describe("Setup + Upload regression", () => {
  test("opens upload surface without the setup wizard", async ({ page }) => {
    await openDataConnections(page);
    await expect(page.getByTestId("onboarding-root")).toHaveCount(0);
    await expect(page.getByRole("tab", { name: /^Upload$/i })).toHaveAttribute("aria-selected", "true");
  });

  test("enables upload processing after file selection", async ({ page }) => {
    await openDataConnections(page);
    await page.getByRole("tab", { name: /^Upload( Data)?$/i }).click();

    const processButton = page.getByRole("button", { name: "Process Upload" });
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
