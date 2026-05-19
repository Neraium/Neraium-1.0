import { expect, test } from "@playwright/test";

async function openGate(page, viewport) {
  await page.setViewportSize(viewport);
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Open Gate settings" })).toBeVisible();
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
    await page.getByRole("button", { name: "Open Gate settings" }).click();
    await expect(page.getByRole("button", { name: /Setup & data connections|Data connections/i })).toBeVisible();
  });
});
