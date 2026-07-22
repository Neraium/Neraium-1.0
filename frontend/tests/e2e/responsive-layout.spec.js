import { expect, test } from "./fixtures.js";

const REQUIRED_VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "laptop", width: 1280, height: 720 },
  { name: "tablet landscape", width: 1024, height: 768 },
  { name: "tablet boundary", width: 768, height: 1024 },
  { name: "mobile large", width: 430, height: 932 },
  { name: "mobile standard", width: 390, height: 844 },
  { name: "mobile medium", width: 375, height: 812 },
  { name: "mobile narrow", width: 320, height: 720 },
  { name: "mobile landscape", width: 844, height: 390 },
];

const COMMAND_CENTER_MOBILE_VIEWPORTS = REQUIRED_VIEWPORTS.filter(({ width }) => width <= 768);
const PRINCIPAL_CARD_SELECTOR = [
  ".operating-state-card",
  ".subsystem-behavior",
  ".priority-finding__card",
  ".command-section--findings",
  ".command-section--systems",
  ".command-section--advanced",
].join(", ");

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

async function commandCenterMobileMetrics(page) {
  return page.evaluate((cardSelector) => {
    const root = document.documentElement;
    const content = document.querySelector(".operational-command-center");
    const contentRect = content?.getBoundingClientRect() ?? null;
    const cardRects = Array.from(document.querySelectorAll(cardSelector))
      .filter((card) => getComputedStyle(card).display !== "none")
      .map((card) => {
        const rect = card.getBoundingClientRect();
        return {
          className: card.className,
          left: rect.left,
          right: rect.right,
          width: rect.width,
          scrollWidth: card.scrollWidth,
          clientWidth: card.clientWidth,
        };
      });
    const header = document.querySelector(".operational-mobile-topbar")?.getBoundingClientRect() ?? null;
    const identity = document.querySelector(".operational-mobile-topbar__identity")?.getBoundingClientRect() ?? null;
    const brandMark = document.querySelector(".operational-mobile-topbar__brand-mark")?.getBoundingClientRect() ?? null;
    const menu = document.querySelector(".operational-mobile-topbar__menu")?.getBoundingClientRect() ?? null;
    const firstCard = content?.firstElementChild?.getBoundingClientRect() ?? null;
    return {
      clientWidth: root.clientWidth,
      scrollWidth: root.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      contentLeft: contentRect?.left ?? null,
      contentRight: contentRect?.right ?? null,
      cards: cardRects,
      headerHeight: header?.height ?? null,
      headerBottom: header?.bottom ?? null,
      identityLeft: identity?.left ?? null,
      brandMarkWidth: brandMark?.width ?? null,
      firstCardTop: firstCard?.top ?? null,
      menuWidth: menu?.width ?? null,
      menuHeight: menu?.height ?? null,
      menuRight: menu?.right ?? null,
    };
  }, PRINCIPAL_CARD_SELECTOR);
}

async function scrollFinalSectionAboveBrowserControls(page) {
  return page.evaluate(() => {
    window.scrollTo(0, document.documentElement.scrollHeight);
    const sections = Array.from(document.querySelectorAll(".operational-command-center > .command-section"));
    const finalSection = sections.at(-1);
    const rect = finalSection?.getBoundingClientRect() ?? null;
    return {
      top: rect?.top ?? null,
      bottom: rect?.bottom ?? null,
      viewportHeight: window.innerHeight,
      bottomClearance: rect ? window.innerHeight - rect.bottom : null,
    };
  });
}

async function openWorkspace(page, viewport) {
  await page.setViewportSize(viewport);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  await expect(page.getByRole("main", { name: "Neraium platform workspace" })).toBeVisible();
}

async function openMobileWorkflowNavigation(page) {
  const menuButton = page.getByRole("button", { name: "Open navigation menu" });
  await expect(menuButton).toBeVisible();
  await menuButton.click();
  const mobileNav = page.getByRole("navigation", { name: "Mobile workflow navigation" });
  await expect(mobileNav).toBeVisible();
  return mobileNav;
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

    const menuButton = page.getByRole("button", { name: "Open navigation menu" });
    await menuButton.focus();
    await expect(menuButton).toBeFocused();
    const focusStyle = await menuButton.evaluate((node) => {
      const style = getComputedStyle(node);
      return { outlineStyle: style.outlineStyle, outlineWidth: Number.parseFloat(style.outlineWidth) };
    });
    expect(focusStyle.outlineStyle).not.toBe("none");
    expect(focusStyle.outlineWidth).toBeGreaterThanOrEqual(2);

    const mobileNav = await openMobileWorkflowNavigation(page);
    await expect(mobileNav.getByRole("button", { name: /Datasets & Connectors/i })).toBeVisible();
  });

  test("Command Center mobile cards preserve gutters and bottom safe space", async ({ page }) => {
    for (const viewport of COMMAND_CENTER_MOBILE_VIEWPORTS) {
      await openWorkspace(page, viewport);
      const metrics = await commandCenterMobileMetrics(page);

      expect(metrics.scrollWidth, `${viewport.name}: document overflow`).toBeLessThanOrEqual(metrics.clientWidth);
      expect(metrics.bodyScrollWidth, `${viewport.name}: body overflow`).toBeLessThanOrEqual(metrics.clientWidth);
      expect(metrics.contentLeft, `${viewport.name}: left page gutter`).toBeGreaterThanOrEqual(15);
      expect(metrics.clientWidth - metrics.contentRight, `${viewport.name}: right page gutter`).toBeGreaterThanOrEqual(15);
      expect(metrics.cards.length, `${viewport.name}: principal cards`).toBeGreaterThan(0);

      for (const card of metrics.cards) {
        expect(card.left, `${viewport.name}: ${card.className} left edge`).toBeGreaterThanOrEqual(0);
        expect(card.right, `${viewport.name}: ${card.className} right edge`).toBeLessThanOrEqual(metrics.clientWidth);
        expect(card.scrollWidth, `${viewport.name}: ${card.className} intrinsic overflow`).toBeLessThanOrEqual(card.clientWidth);
      }

      if (viewport.width <= 768) {
        expect(metrics.identityLeft, `${viewport.name}: left-aligned header identity`).toBeGreaterThanOrEqual(15);
        expect(metrics.identityLeft, `${viewport.name}: left-aligned header identity`).toBeLessThanOrEqual(20);
        expect(metrics.brandMarkWidth, `${viewport.name}: visible brand mark`).toBeGreaterThanOrEqual(28);
        expect(metrics.menuWidth, `${viewport.name}: menu touch width`).toBeGreaterThanOrEqual(44);
        expect(metrics.menuHeight, `${viewport.name}: menu touch height`).toBeGreaterThanOrEqual(44);
        expect(metrics.menuRight, `${viewport.name}: menu button right edge`).toBeLessThanOrEqual(metrics.clientWidth);
        expect(metrics.headerHeight, `${viewport.name}: compact mobile header`).toBeLessThanOrEqual(64);
        expect(metrics.firstCardTop - metrics.headerBottom, `${viewport.name}: header-to-card gap`).toBeLessThanOrEqual(12);
      }

      const finalSection = await scrollFinalSectionAboveBrowserControls(page);
      expect(finalSection.top, `${viewport.name}: final section top`).toBeGreaterThanOrEqual(0);
      expect(finalSection.bottom, `${viewport.name}: final section bottom`).toBeLessThanOrEqual(finalSection.viewportHeight);
      expect(finalSection.bottomClearance, `${viewport.name}: browser-control clearance`).toBeGreaterThanOrEqual(64);
    }
  });

  test("mobile workflow navigation remains visible and usable", async ({ page }) => {
    await openWorkspace(page, { width: 390, height: 844 });
    const mobileNav = await openMobileWorkflowNavigation(page);
    await mobileNav.getByRole("button", { name: /Datasets & Connectors/i }).click();
    await expect(page.getByRole("region", { name: "Import a dataset" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Choose CSV file" })).toBeVisible();
  });

  test("empty Command Center import action opens the upload card at the top on mobile", async ({ page }) => {
    await openWorkspace(page, { width: 390, height: 844 });
    await expect(page.getByText("Awaiting data", { exact: true })).toBeVisible();
    await expect(page.getByText("Watching", { exact: true })).toHaveCount(0);

    await page.getByRole("button", { name: "Import dataset" }).click();

    const importCard = page.getByRole("region", { name: "Import a dataset" });
    const sourceStatus = page.getByRole("region", { name: "Data Source Status" });
    await expect(importCard).toBeVisible();
    await expect(page.getByRole("button", { name: "Choose CSV file" })).toBeVisible();
    await expect(page).toHaveURL(/section=data-sources.*#import-dataset$/);
    await expect(page.getByRole("heading", { name: "Available Imports" })).toHaveCount(0);

    const metrics = await page.evaluate(() => {
      const card = document.querySelector("#import-dataset")?.getBoundingClientRect();
      const status = document.querySelector('[aria-label="Data Source Status"]')?.getBoundingClientRect();
      const header = document.querySelector(".operational-mobile-topbar")?.getBoundingClientRect();
      return {
        cardTop: card?.top ?? null,
        cardBottom: card?.bottom ?? null,
        statusTop: status?.top ?? null,
        headerBottom: header?.bottom ?? null,
        viewportHeight: window.innerHeight,
      };
    });
    expect(metrics.cardTop).toBeGreaterThanOrEqual(metrics.headerBottom - 1);
    expect(metrics.cardBottom).toBeLessThan(metrics.viewportHeight);
    expect(metrics.cardBottom).toBeLessThan(metrics.statusTop);
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
      await expect(page.getByRole("heading", { name: "Current state" })).toBeVisible();
    }
  });

  test("buttons do not overlap across responsive widths", async ({ page }) => {
    for (const viewport of REQUIRED_VIEWPORTS) {
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
