import { readFileSync } from "node:fs";
import { expect, governedComparisonResult, test } from "./fixtures.js";

const cases = JSON.parse(readFileSync(new URL("../fixtures/presentation-phase1.json", import.meta.url), "utf8"));
const fallbackCase = JSON.parse(readFileSync(new URL("../fixtures/presentation-phase1-context-fallback.json", import.meta.url), "utf8"));

const graphFallbackCase = JSON.parse(readFileSync(new URL("../fixtures/presentation-phase1-graph-fallback.json", import.meta.url), "utf8"));

for (const [name, width] of [["A", 1440], ["B", 390], ["fallback", 390], ["graph-fallback", 1440], ["graph-fallback", 390]]) {
  test(`case ${name} at ${width}px preserves the assessment while opening bounded relationship evidence`, async ({ page, context }) => {
    // Preserve the issued opaque cookie; the shared fixture substitutes a public
    // session id, which is not a credential under the current auth contract.
    const api = `http://127.0.0.1:${Number(process.env.PLAYWRIGHT_BACKEND_PORT || 8012)}`;
    const login = await context.request.post(`${api}/api/auth/login`, { data: { email: "e2e-admin@neraium.test", password: "e2e-password-123" } });
    expect(login.ok()).toBe(true);
    const cookies = await context.cookies(api);
    await context.addCookies(cookies.map((cookie) => ({ ...cookie, secure: false })));

    const evidence = name === "graph-fallback" ? graphFallbackCase.evidence : name === "fallback" ? fallbackCase.evidence : cases.find((item) => item.case === name).evidence;
    const result = governedComparisonResult({
      job_id: "presentation-phase1", facility_name: "Controlled test system",
      sii_reliable_enough_to_show: name !== "B", evidence_persisted: true,
      data_quality: { coverage_percent: 100 },
      analysis_result: { analysis_id: "presentation-phase1", systems: [], relationships: [], insights: [], conditions: [], evidence_index: {} },
      relationship_observations: evidence,
    });
    await page.setViewportSize({ width, height: 900 });
    await page.route("**/api/data/analyses/presentation-phase1", (route) => route.fulfill({ json: result }));
    await page.route("**/api/evidence/runs**", (route) => route.fulfill({ json: { runs: [] } }));
    await page.goto("/analyses/presentation-phase1");
    const brief = page.getByTestId("operations-brief");
    await expect(brief).toBeVisible();
    const before = await brief.innerText();
    if (name === "B") expect(before).toContain("Insufficient evidence");
    const disclosure = page.locator(".relationship-observations");
    await expect(disclosure).not.toHaveAttribute("open", "");
    await disclosure.locator(":scope > summary").click();
    await expect(disclosure.getByText("Relationships evaluated", { exact: true })).toBeVisible();
    await disclosure.locator(":scope > details > summary").first().click();
    await expect(disclosure.getByText("Single-window change", { exact: true }).first()).toBeVisible();
    await expect(disclosure.getByText("Persistent relationship change", { exact: true }).first()).toBeVisible();
    if (name === "fallback") {
      const relationship = disclosure.locator(":scope > details").first();
      await expect(relationship.getByText("General operating-mode match", { exact: true })).toBeVisible();
      await expect(relationship.locator("dt", { hasText: "General operating-mode match" }).locator("..")).toContainText("strong");
      await expect(relationship.getByText("Global relationship model", { exact: true })).toBeVisible();
      await expect(relationship.locator("dt", { hasText: "Like-mode comparison status" }).locator("..")).toContainText("Limited");
      await expect(relationship.locator("dt", { hasText: "Global fallback used" }).locator("..")).toContainText("Yes");
      await expect(relationship.getByText("Too few recent samples in this operating mode.", { exact: true })).toBeVisible();
      await expect(disclosure).not.toContainText("insufficient_recent_mode_rows");
    }
    if (name === "graph-fallback") {
      const relationship = disclosure.locator(":scope > details").first();
      await expect(relationship.getByText("Global relationship model", { exact: true })).toBeVisible();
      await expect(relationship.getByText("Dynamic relationship comparison was unavailable for this evaluation.", { exact: true })).toBeVisible();
      await expect(disclosure).not.toContainText("global_relationship_model_failure_fallback");
      await expect(disclosure).not.toContainText("CANARY");
      await expect(disclosure.locator('[role="alert"]')).toHaveCount(0);
    }
    expect(await brief.innerText()).toBe(before);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    await expect(disclosure.locator("button,input,form")).toHaveCount(0);
  });
}
