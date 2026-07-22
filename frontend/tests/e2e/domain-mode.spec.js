import { expect, test } from "./fixtures.js";

test.describe("Domain mode wiring", () => {
  test("shows the backend-detected data type in collapsed technical details", async ({ page }) => {
    let mode = "aquatic";
    await page.route("**/api/domain/mode*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ mode, source: "upload_shape", confidence: 0.88, evidence: ["pool_water_temp"], supported_modes: ["aquatic", "cultivation"], profile: {} }) }));
    await page.route("**/api/facility/systems*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ systems: [], domain_mode: mode, domain_source: "upload_shape", domain_confidence: 0.88, domain_evidence: [mode === "aquatic" ? "pool_water_temp" : "cultivation_temp"] }) }));
    const result = { job_id: "domain-run", facility_name: "Domain Site", sii_completed: true, sii_reliable_enough_to_show: true, analysis_explanation: { systems: [], relationships: [], insights: [] } };
    const current = { status: "complete", job_id: "domain-run", result };
    await page.route("**/api/data/latest-upload**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "complete", sii_completed: true, latest_result: result, current_upload: current, snapshot: { status: "complete", sii_completed: true, latest_result: result, current_upload: current } }) }));
    await page.goto("/sites/current", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    await page.getByRole("button", { name: /Scores, identifiers, and processing metadata/ }).click();
    await expect(page.getByText("Detected data type")).toBeVisible();
    await expect(page.getByText("Water Infrastructure")).toBeVisible();

    mode = "cultivation";
    await page.unroute("**/api/domain/mode*");
    await page.route("**/api/domain/mode*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ mode, source: "upload_shape", confidence: 0.88, evidence: ["cultivation_temp"], supported_modes: ["aquatic", "cultivation"], profile: {} }) }));
    const cultivationResponse = page.waitForResponse((response) => response.url().includes("/api/domain/mode"));
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect((await cultivationResponse).json()).resolves.toMatchObject({ mode: "cultivation" });
    await page.getByRole("button", { name: /Scores, identifiers, and processing metadata/ }).click();
    await expect(page.getByText("Cultivation")).toBeVisible();
  });
});
