import { expect, test } from "./fixtures.js";

test.describe("Engineering workspace resilience", () => {
  test("malformed optional analysis collections do not crash portfolio triage", async ({ page }) => {
    const result = { job_id: "partial-run", facility_name: "Partial Site", sii_completed: true, sii_reliable_enough_to_show: true, analysis_explanation: { systems: {}, relationships: null, insights: "not-an-array" }, data_quality: { warnings: ["Evidence collection incomplete"] } };
    const current = { status: "complete", job_id: "partial-run", result };
    await page.route("**/api/data/latest-upload**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "complete", sii_completed: true, latest_result: result, current_upload: current, snapshot: { status: "complete", latest_result: result, current_upload: current } }) }));
    await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("engineering-reasoning-platform")).toBeVisible();
    await expect(page.locator("body")).not.toContainText("We hit a workspace error");
    await expect(page.getByText("Partial Site").first()).toBeVisible();
  });

  test("an unavailable evidence-history request leaves the current site usable", async ({ page }) => {
    await page.route("**/api/evidence/runs**", (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "temporarily unavailable" }) }));
    await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: /Where does the evidence warrant attention/i })).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();
  });

  test("direct investigation links with unavailable evidence degrade to a clear empty state", async ({ page }) => {
    await page.goto("/investigations/missing", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "No analyzed telemetry is available" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Open data connections" })).toBeVisible();
  });
});
