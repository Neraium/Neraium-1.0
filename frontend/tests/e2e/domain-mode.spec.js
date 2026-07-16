import { expect, test } from "./fixtures.js";

async function openAdvanced(page) {
  const advancedButton = page.getByRole("button", { name: /Advanced/i }).first();
  await expect(advancedButton).toBeVisible();
  await advancedButton.click();
  await expect(page.getByRole("region", { name: "Telemetry source details" })).toBeVisible();
}

test.describe("Domain mode wiring", () => {
  test("shows the detected data type from the backend", async ({ page }) => {
    let mode = "aquatic";
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
    await page.route("**/api/domain/mode*", async (route) => {
      const request = route.request();
      if (request.method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            mode,
            source: "upload_shape",
            confidence: 0.88,
            evidence: ["pool_water_temp", "orp_mv", "chlorine_ppm"],
            supported_modes: ["aquatic", "cultivation"],
            profile: {
              subtitle: "",
              description: "",
              replay_demo_mode: "aquatic_demo",
            },
          }),
        });
        return;
      }
      await route.continue();
    });
    await page.route("**/api/facility/systems*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          systems: mode === "aquatic" ? [{ name: "Circulation", scope: "" }] : [{ name: "HVAC", scope: "" }],
          driver_categories: [],
          domain_mode: mode,
          domain_source: "upload_shape",
          domain_confidence: 0.88,
          domain_evidence: ["detected columns"],
          intelligence: {},
          adaptive_learning: {},
          integration_stubs: [],
          intelligence_status: {},
        }),
      });
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    await openAdvanced(page);
    await expect(page.getByText("Detected data type")).toBeVisible();
    await expect(page.getByText(/Water Infrastructure|Aquatic|Cultivation/).first()).toBeVisible();

    mode = "cultivation";

    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    await openAdvanced(page);
    await expect(page.getByText("Detected data type")).toBeVisible();
    await expect(page.getByText(/Water Infrastructure|Aquatic|Cultivation/).first()).toBeVisible();
  });
});
