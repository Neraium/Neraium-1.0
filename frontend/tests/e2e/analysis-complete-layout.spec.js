import { expect, test } from "@playwright/test";

async function renderCompletionFixture(page) {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.getComputedStyle(document.documentElement).getPropertyValue("--text-primary").trim().length > 0);

  await page.evaluate(() => {
    document.body.innerHTML = `
      <main data-testid="completion-fixture" style="width: 100%; max-width: 100vw; padding: 12px;">
        <form class="intake-flow intake-flow--simple intake-flow--complete" style="width: 100%; max-width: 100%;">
          <section class="upload-simple-card upload-simple-card--complete" aria-label="Analysis complete">
            <div class="upload-complete-header">
              <h3>Analysis Complete</h3>
              <span class="upload-complete-filename" title="neraium_water_test_dataset_2.csv">neraium_water_test_dataset_2.csv</span>
            </div>
            <div class="upload-result-summary">
              <div class="upload-result-summary__item"><span>Systems</span><strong>4</strong></div>
              <div class="upload-result-summary__item"><span>Insights</span><strong>2</strong></div>
              <div class="upload-result-summary__item"><span>Fingerprint</span><strong>Changed</strong></div>
            </div>
            <div class="upload-simple-actions">
              <button type="button" class="command-button">View Results</button>
              <button type="button" class="secondary-command-button">Analyze Another CSV</button>
            </div>
          </section>
          <details class="upload-advanced-details">
            <summary>Advanced Details</summary>
            <dl class="upload-advanced-details__grid">
              <div><dt>Upload ID</dt><dd>job-complete</dd></div>
            </dl>
          </details>
        </form>
      </main>
    `;
  });
}

async function visibleAtCenter(locator) {
  return locator.evaluate((node) => {
    const rect = node.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    const topNode = document.elementFromPoint(centerX, centerY);
    return Boolean(rect.width > 0 && rect.height > 0 && topNode && (topNode === node || node.contains(topNode)));
  });
}

test.describe("Analysis complete mobile layout", () => {
  test("uses stacked compact summary without overflow", async ({ page }) => {
    await renderCompletionFixture(page);

    const metrics = await page.evaluate(() => {
      const root = document.documentElement;
      const body = document.body;
      const card = document.querySelector(".upload-simple-card--complete").getBoundingClientRect();
      return {
        viewportWidth: window.innerWidth,
        scrollWidth: root.scrollWidth,
        bodyScrollWidth: body.scrollWidth,
        cardLeft: card.left,
        cardRight: card.right,
      };
    });

    expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.viewportWidth);
    expect(metrics.bodyScrollWidth).toBeLessThanOrEqual(metrics.viewportWidth);
    expect(metrics.cardLeft).toBeGreaterThanOrEqual(0);
    expect(metrics.cardRight).toBeLessThanOrEqual(metrics.viewportWidth);

    const rows = await page.locator(".upload-result-summary__item").evaluateAll((nodes) => (
      nodes.map((node) => {
        const rect = node.getBoundingClientRect();
        return { left: rect.left, top: rect.top, bottom: rect.bottom, width: rect.width };
      })
    ));

    expect(rows).toHaveLength(3);
    expect(rows[1].top).toBeGreaterThanOrEqual(rows[0].bottom - 1);
    expect(rows[2].top).toBeGreaterThanOrEqual(rows[1].bottom - 1);
    expect(Math.abs(rows[0].left - rows[1].left)).toBeLessThanOrEqual(1);
    expect(Math.abs(rows[1].left - rows[2].left)).toBeLessThanOrEqual(1);
    rows.forEach((row) => expect(row.width).toBeLessThanOrEqual(metrics.viewportWidth));
  });

  test("keeps primary transition controls and secondary details in the right state", async ({ page }) => {
    await renderCompletionFixture(page);

    await expect(page.getByRole("button", { name: "View Results" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Analyze Another CSV" })).toBeVisible();

    const fingerprintValue = page.locator(".upload-result-summary__item", { hasText: "Fingerprint" }).locator("strong");
    await expect(fingerprintValue).toHaveText("Changed");
    expect(await visibleAtCenter(fingerprintValue)).toBe(true);

    const buttonRects = await page.locator(".upload-simple-actions button").evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().top));
    expect(buttonRects[1]).toBeGreaterThan(buttonRects[0]);

    const completeCardStyle = await page.locator(".upload-simple-card--complete").evaluate((node) => {
      const style = window.getComputedStyle(node);
      return { borderColor: style.borderTopColor, backgroundColor: style.backgroundColor };
    });
    expect(completeCardStyle.borderColor).not.toContain("34, 197, 94");
    expect(completeCardStyle.backgroundColor).not.toContain("8, 116, 67");

    const detailsOpen = await page.locator(".upload-advanced-details").evaluate((node) => node.open);
    expect(detailsOpen).toBe(false);
  });
});
