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
              <div class="upload-result-summary__item"><span>Baseline</span><strong>Changed</strong></div>
            </div>
            <div class="upload-simple-actions">
              <button type="button" class="command-button">View Results</button>
              <button type="button" class="secondary-command-button">Analyze New Telemetry</button>
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


async function renderInsightCompletionFixture(page) {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".operational-workflow");
  await page.waitForFunction(() => {
    const workflow = document.querySelector(".operational-workflow");
    return Boolean(workflow && window.getComputedStyle(workflow).getPropertyValue("--ops-ink").trim());
  });

  await page.evaluate(() => {
    document.body.innerHTML = "";
    const root = document.createElement("div");
    root.className = "page-container operational-workflow";
    root.dataset.testid = "insight-contrast-fixture";
    root.innerHTML = [
      "<main class=\"operational-main\">",
      "<section class=\"operational-panel operational-panel--hero operational-panel--wide\" aria-label=\"Executive summary\">",
      "<div class=\"operator-summary-card\">",
      "<div class=\"operational-panel__header operational-panel__header--tight\">",
      "<span class=\"section-token\">Overview</span>",
      "<h2>Analysis Complete</h2>",
      "<p>Historical telemetry analyzed.</p>",
      "</div>",
      "<div class=\"operator-executive-summary\" aria-label=\"Executive summary rows\">",
      "<ul class=\"operator-completion-list\" aria-label=\"Analysis completion checks\">",
      "<li><span aria-hidden=\"true\">OK</span><strong>Systems identified</strong></li>",
      "<li><span aria-hidden=\"true\">OK</span><strong>Relationship changes detected</strong></li>",
      "<li><span aria-hidden=\"true\">OK</span><strong>Baseline updated</strong></li>",
      "</ul>",
      "<section class=\"operator-interpretation__block\" aria-label=\"Rendered content below checks\">",
      "<h3 data-testid=\"below-checklist-heading\">Operator briefing remains readable</h3>",
      "<p data-testid=\"below-checklist-body\">Section titles and body copy below the completion badges render at normal contrast.</p>",
      "</section>",
      "<dl class=\"executive-summary-list\">",
      "<div class=\"executive-summary-item\"><dt>Overall Status</dt><dd data-testid=\"below-checklist-value\">Normal operation</dd></div>",
      "<div class=\"executive-summary-item\"><dt>Recommended Next Check</dt><dd>Continue monitoring</dd></div>",
      "</dl>",
      "</div>",
      "</div>",
      "</section>",
      "</main>",
    ].join("");
    document.body.append(root);
  });
}

function parseRgb(value) {
  const match = String(value).match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([0-9.]+))?\)/);
  if (!match) return null;
  return { r: Number(match[1]), g: Number(match[2]), b: Number(match[3]), a: match[4] === undefined ? 1 : Number(match[4]) };
}

function relativeLuminance({ r, g, b }) {
  const values = [r, g, b].map((channel) => {
    const value = channel / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return (0.2126 * values[0]) + (0.7152 * values[1]) + (0.0722 * values[2]);
}

function contrastRatio(foreground, background) {
  const foregroundLum = relativeLuminance(foreground);
  const backgroundLum = relativeLuminance(background);
  const lighter = Math.max(foregroundLum, backgroundLum);
  const darker = Math.min(foregroundLum, backgroundLum);
  return (lighter + 0.05) / (darker + 0.05);
}

test.describe("Insight completion rendering", () => {
  test("keeps content below success badges readable on an iPhone-sized viewport", async ({ page }) => {
    await renderInsightCompletionFixture(page);

    const rendering = await page.locator("[data-testid=insight-contrast-fixture]").evaluate((root) => {
      const panel = root.querySelector(".operational-panel");
      const checklistItem = root.querySelector(".operator-completion-list li");
      const heading = root.querySelector("[data-testid=below-checklist-heading]");
      const body = root.querySelector("[data-testid=below-checklist-body]");
      const value = root.querySelector("[data-testid=below-checklist-value]");
      const guardedNodes = [
        root.querySelector(".operator-completion-list"),
        checklistItem,
        root.querySelector(".operator-executive-summary"),
        root.querySelector(".operator-interpretation__block"),
        root.querySelector(".executive-summary-list"),
      ].filter(Boolean);

      function styleSnapshot(node) {
        const style = window.getComputedStyle(node);
        return {
          opacity: style.opacity,
          filter: style.filter,
          backdropFilter: style.backdropFilter || style.webkitBackdropFilter || "none",
          mixBlendMode: style.mixBlendMode,
          transform: style.transform,
          isolation: style.isolation,
          backgroundColor: style.backgroundColor,
          backgroundImage: style.backgroundImage,
          color: style.color,
        };
      }

      const headingRect = heading.getBoundingClientRect();
      const centerNode = document.elementFromPoint(headingRect.left + (headingRect.width / 2), headingRect.top + (headingRect.height / 2));

      return {
        panel: styleSnapshot(panel),
        checklistItem: styleSnapshot(checklistItem),
        heading: styleSnapshot(heading),
        body: styleSnapshot(body),
        value: styleSnapshot(value),
        guarded: guardedNodes.map(styleSnapshot),
        headingIsTopmost: centerNode === heading || heading.contains(centerNode),
      };
    });

    expect(rendering.panel.backgroundColor).toBe("rgb(13, 20, 31)");
    expect(rendering.panel.backgroundImage).toBe("none");
    expect(rendering.checklistItem.backgroundColor).toBe("rgb(18, 29, 44)");
    expect(rendering.checklistItem.backgroundImage).toBe("none");
    expect(rendering.headingIsTopmost).toBe(true);

    for (const style of rendering.guarded) {
      expect(style.opacity).toBe("1");
      expect(style.filter).toBe("none");
      expect(style.backdropFilter).toBe("none");
      expect(style.mixBlendMode).toBe("normal");
      expect(style.transform).toBe("none");
      expect(style.isolation).toBe("auto");
    }

    const panelBackground = parseRgb(rendering.panel.backgroundColor);
    expect(contrastRatio(parseRgb(rendering.heading.color), panelBackground)).toBeGreaterThan(4.5);
    expect(contrastRatio(parseRgb(rendering.body.color), panelBackground)).toBeGreaterThan(4.5);
    expect(contrastRatio(parseRgb(rendering.value.color), panelBackground)).toBeGreaterThan(4.5);
  });
});

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
    await expect(page.getByRole("button", { name: "Analyze New Telemetry" })).toBeVisible();

    const fingerprintValue = page.locator(".upload-result-summary__item", { hasText: "Baseline" }).locator("strong");
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
