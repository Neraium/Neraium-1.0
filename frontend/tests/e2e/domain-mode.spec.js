import { expect, test } from "@playwright/test";

async function openSettings(page) {
  const settingsButton = page.getByRole("button", { name: "Open Gate settings" });
  await expect(settingsButton).toBeVisible();
  await settingsButton.click();
  return settingsButton;
}

test.describe("Domain mode wiring", () => {
  test("switches between aquatic and cultivation and persists across reload", async ({ page }) => {
    let mode = "aquatic";
    await page.route("**/api/domain/mode*", async (route) => {
      const request = route.request();
      if (request.method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            mode,
            supported_modes: ["aquatic", "cultivation"],
            profile: {},
          }),
        });
        return;
      }
      if (request.method() === "POST") {
        const payload = request.postDataJSON?.() ?? {};
        mode = payload.mode === "cultivation" ? "cultivation" : "aquatic";
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            mode,
            updated_at: new Date().toISOString(),
            profile: {},
          }),
        });
        return;
      }
      await route.continue();
    });

    await page.goto("/");
    await openSettings(page);

    const toCultivation = page.getByRole("button", { name: "Switch to cultivation mode" });
    const toAquatic = page.getByRole("button", { name: "Switch to aquatic mode" });
    let expectedAfterReload;

    if (await toCultivation.isVisible()) {
      expectedAfterReload = page.getByRole("button", { name: "Switch to aquatic mode" });
      await toCultivation.click();
      await expect(expectedAfterReload).toBeVisible();
    } else {
      await expect(toAquatic).toBeVisible();
      expectedAfterReload = page.getByRole("button", { name: "Switch to cultivation mode" });
      await toAquatic.click();
      await expect(expectedAfterReload).toBeVisible();
    }

    await page.reload();
    await openSettings(page);
    await expect(expectedAfterReload).toBeVisible();
  });
});
