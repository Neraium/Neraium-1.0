import { expect, test } from "./fixtures.js";

test.describe("mobile production onboarding", () => {
  test.skip(({ browserName }) => browserName === "firefox", "Firefox does not support Playwright's mobile context option; WebKit covers this mobile Safari contract.");
  test.use({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });

  test("the Data Connections action is the topmost tap target and opens read-only setup", async ({ page }) => {
    await page.goto("/workspace/data-sources", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    await expect(page.getByRole("heading", { name: "Connect a physical system", level: 1 })).toBeVisible();
    await expect(page.getByTestId("csv-upload-input")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Import Historical Dataset" })).toHaveCount(0);

    const button = page.getByRole("button", { name: "Add data source" }).first();
    await expect(button).toBeEnabled();
    const isTopmostTapTarget = await button.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return Boolean(hit && (hit === element || element.contains(hit)));
    });
    expect(isTopmostTapTarget).toBe(true);

    await button.tap();
    await expect(page.getByRole("heading", { name: "Add a read-only data source", level: 2 })).toBeVisible();
    await expect(page.getByText("Retrieval only", { exact: true })).toBeVisible();
    await expect(page.getByText(/accepts no browser-supplied SQL, DSN, file path, HTTP method, or command/i)).toBeVisible();
    await expect(page.locator("body")).not.toContainText("We hit a workspace error");
  });
});
