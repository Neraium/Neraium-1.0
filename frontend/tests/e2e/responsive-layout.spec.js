import { expect, test } from "./fixtures.js";

const REQUIRED_VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "laptop", width: 1280, height: 720 },
  { name: "tablet landscape", width: 1024, height: 768 },
  { name: "tablet portrait", width: 768, height: 1024 },
  { name: "mobile portrait", width: 390, height: 844 },
  { name: "mobile landscape", width: 844, height: 390 },
];

async function visibleButtonRects(page) {
  return page.evaluate(() => {
    const nodes = Array.from(document.querySelectorAll("button, [role='button'], .command-button, .secondary-command-button, .btn"));
    return nodes
      .map((node, index) => {
        const style = window.getComputedStyle(node);
        const rect = node.getBoundingClientRect();
        const label = (node.getAttribute("aria-label") || node.textContent || node.className || `button-${index}`).trim().replace(/\s+/g, " ");
        const centerX = rect.left + (rect.width / 2);
        const centerY = rect.top + (rect.height / 2);
        const topNode = document.elementFromPoint(centerX, centerY);
        return {
          index,
          label,
          x: rect.x,
          y: rect.y,
          right: rect.right,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
          visible: style.visibility !== "hidden"
            && style.display !== "none"
            && rect.width > 0
            && rect.height > 0
            && (!topNode || topNode === node || node.contains(topNode)),
        };
      })
      .filter((rect) => rect.visible);
  });
}

function findOverlappingRects(rects) {
  const overlaps = [];
  for (let i = 0; i < rects.length; i += 1) {
    for (let j = i + 1; j < rects.length; j += 1) {
      const a = rects[i];
      const b = rects[j];
      const horizontal = Math.min(a.right, b.right) - Math.max(a.x, b.x);
      const vertical = Math.min(a.bottom, b.bottom) - Math.max(a.y, b.y);
      if (horizontal > 1 && vertical > 1) {
        overlaps.push(`${a.label} overlaps ${b.label}`);
      }
    }
  }
  return overlaps;
}

async function expectNoVisibleButtonOverlap(page) {
  const overlaps = findOverlappingRects(await visibleButtonRects(page));
  expect(overlaps, overlaps.join("\n")).toEqual([]);
}

async function operationalLayoutMetrics(page) {
  return page.evaluate(() => {
    const main = document.querySelector('.operational-main');
    const hero = document.querySelector('.command-center-hero') ?? main;
    const root = document.documentElement;
    const body = document.body;
    const mainRect = main?.getBoundingClientRect() ?? null;
    const heroRect = hero?.getBoundingClientRect() ?? null;
    return {
      viewportWidth: window.innerWidth,
      scrollWidth: root.scrollWidth,
      bodyScrollWidth: body.scrollWidth,
      mainLeft: mainRect?.left ?? null,
      mainRight: mainRect?.right ?? null,
      mainWidth: mainRect?.width ?? null,
      heroLeft: heroRect?.left ?? null,
      heroRight: heroRect?.right ?? null,
      heroWidth: heroRect?.width ?? null,
    };
  });
}

async function openWorkspace(page, viewport) {
  await page.setViewportSize(viewport);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  await expect(page.getByRole("main", { name: "Neraium platform workspace" })).toBeVisible();
}

test.describe("Responsive layout audit", () => {
  test("desktop operational workspace uses full available width", async ({ page }) => {
    await openWorkspace(page, { width: 1440, height: 900 });
    const main = page.locator(".operational-main");
    await expect(main).toBeVisible();
    const box = await main.boundingBox();
    expect(box).not.toBeNull();
    expect(box.width).toBeGreaterThan(900);
  });

  test("tablet operational workspace remains centered and usable", async ({ page }) => {
    await openWorkspace(page, { width: 1024, height: 1366 });
    const main = page.locator(".operational-main");
    await expect(main).toBeVisible();
    const box = await main.boundingBox();
    expect(box).not.toBeNull();
    expect(box.width).toBeGreaterThan(700);
  });

  test("mobile operational workspace has no horizontal overflow", async ({ page }) => {
    await openWorkspace(page, { width: 390, height: 844 });

    const metrics = await operationalLayoutMetrics(page);

    expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.viewportWidth);
    expect(metrics.bodyScrollWidth).toBeLessThanOrEqual(metrics.viewportWidth);
    expect(metrics.mainWidth).toBeLessThanOrEqual(metrics.viewportWidth);
    expect(metrics.heroWidth).toBeLessThanOrEqual(metrics.viewportWidth);
    expect(metrics.mainLeft).toBeGreaterThanOrEqual(0);
    expect(metrics.heroLeft).toBeGreaterThanOrEqual(0);
    expect(metrics.mainRight).toBeLessThanOrEqual(metrics.viewportWidth);
    expect(metrics.heroRight).toBeLessThanOrEqual(metrics.viewportWidth);

    await expect(page.getByRole("button", { name: /Datasets & Connectors/i }).first()).toBeVisible();
  });

  test("mobile workflow navigation remains visible and usable", async ({ page }) => {
    await openWorkspace(page, { width: 390, height: 844 });
    await page.getByRole("button", { name: /Datasets & Connectors/i }).first().click();
    await expect(page.getByRole("region", { name: "Dataset Analysis" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Choose Dataset/i })).toBeVisible();
  });

  test("required production viewports avoid document overflow and clipping", async ({ page }) => {
    for (const viewport of REQUIRED_VIEWPORTS) {
      await openWorkspace(page, viewport);
      const metrics = await operationalLayoutMetrics(page);
      expect(metrics.scrollWidth, viewport.name).toBeLessThanOrEqual(metrics.viewportWidth + 1);
      expect(metrics.bodyScrollWidth, viewport.name).toBeLessThanOrEqual(metrics.viewportWidth + 1);
      expect(metrics.mainLeft, viewport.name).toBeGreaterThanOrEqual(0);
      expect(metrics.mainRight, viewport.name).toBeLessThanOrEqual(metrics.viewportWidth + 1);
      expect(metrics.heroLeft, viewport.name).toBeGreaterThanOrEqual(0);
      expect(metrics.heroRight, viewport.name).toBeLessThanOrEqual(metrics.viewportWidth + 1);
      await expect(page.getByRole("heading", { name: "Operational Status" })).toBeVisible();
    }
  });

  test("buttons do not overlap across responsive widths", async ({ page }) => {
    const viewports = [
      { name: "narrow window", width: 320, height: 720 },
      ...REQUIRED_VIEWPORTS,
    ];

    for (const viewport of viewports) {
      await openWorkspace(page, viewport);
      await expectNoVisibleButtonOverlap(page);
    }
  });

  test("touch controls meet the WCAG 2.2 minimum target size", async ({ page }) => {
    for (const viewport of REQUIRED_VIEWPORTS.filter(({ name }) => name.startsWith("mobile"))) {
      await openWorkspace(page, viewport);
      const undersized = (await visibleButtonRects(page))
        .filter(({ width, height }) => width < 24 || height < 24)
        .map(({ label, width, height }) => `${label}: ${width.toFixed(1)}x${height.toFixed(1)}`);
      expect(undersized, `${viewport.name}: ${undersized.join("; ")}`).toEqual([]);
    }
  });
});
