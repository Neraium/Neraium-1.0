import { expect, test } from "@playwright/test";


async function visibleButtonRects(page) {
  return page.evaluate(() => {
    const nodes = Array.from(document.querySelectorAll("button, [role='button'], .command-button, .secondary-command-button, .btn"));
    return nodes
      .map((node, index) => {
        const style = window.getComputedStyle(node);
        const rect = node.getBoundingClientRect();
        const label = (node.getAttribute("aria-label") || node.textContent || node.className || `button-${index}`).trim().replace(/\s+/g, " ");
        return {
          index,
          label,
          x: rect.x,
          y: rect.y,
          right: rect.right,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
          visible: style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0,
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

async function openGate(page, viewport) {
  await page.setViewportSize(viewport);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
  await expect(page.getByRole("button", { name: /Open Gate settings|Open workspace menu/ })).toBeVisible();
}

test.describe("Responsive layout audit", () => {
  test("desktop gate uses full workspace width", async ({ page }) => {
    await openGate(page, { width: 1440, height: 900 });
    const gate = page.locator(".system-gate");
    await expect(gate).toBeVisible();
    const box = await gate.boundingBox();
    expect(box).not.toBeNull();
    expect(box.width).toBeGreaterThan(900);
  });

  test("tablet gate remains centered and usable", async ({ page }) => {
    await openGate(page, { width: 1024, height: 1366 });
    const gate = page.locator(".system-gate");
    await expect(gate).toBeVisible();
    const box = await gate.boundingBox();
    expect(box).not.toBeNull();
    expect(box.width).toBeGreaterThan(700);
  });

  test("mobile gate and settings are reachable", async ({ page }) => {
    await openGate(page, { width: 390, height: 844 });
    await page.getByRole("button", { name: /Open Gate settings|Open workspace menu/ }).click();
    await expect(page.getByRole("button", { name: /Setup & data connections|Data connections|Upload CSV \/ Connect Data/i })).toBeVisible();
  });

  test("buttons do not overlap across responsive widths", async ({ page }) => {
    const viewports = [
      { width: 320, height: 720 },
      { width: 375, height: 812 },
      { width: 390, height: 844 },
      { width: 430, height: 932 },
      { width: 768, height: 1024 },
      { width: 1440, height: 900 },
    ];

    for (const viewport of viewports) {
      await openGate(page, viewport);
      await expectNoVisibleButtonOverlap(page);

      await page.getByRole("button", { name: /Open Gate settings|Open workspace menu/ }).click();
      await expectNoVisibleButtonOverlap(page);

      await page.getByRole("button", { name: /Setup & data connections|Data connections|Upload CSV \/ Connect Data/i }).click();
      await expect(page.getByRole("button", { name: /Back to Gate/i })).toBeVisible();
      await expectNoVisibleButtonOverlap(page);
    }
  });

});
