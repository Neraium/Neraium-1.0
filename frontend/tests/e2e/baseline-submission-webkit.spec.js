import { expect, test } from "./fixtures.js";

test.describe("mobile Safari baseline submission", () => {
  test.use({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });

  test("the baseline button is the topmost tap target and immediately starts the current upload", async ({ page }) => {
    let uploadRequests = 0;
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.pathname === "/api/data/upload" && request.method() === "POST") uploadRequests += 1;
    });
    await page.route("**/api/data/upload", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 750));
      await route.continue();
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    await page.getByRole("button", { name: "Import Historical Dataset", exact: true }).tap();
    await expect(page.getByRole("heading", { name: "Import Historical Dataset", level: 2 })).toBeVisible();

    await page.getByTestId("csv-upload-input").setInputFiles({
      name: "mobile-safari.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(
        "timestamp,room,temperature,humidity\n2026-05-01T08:00:00Z,Plant,75.2,58\n2026-05-01T08:05:00Z,Plant,75.5,59\n",
        "utf8",
      ),
    });

    const button = page.getByRole("button", { name: "Start Baseline Analysis" });
    await expect(button).toBeEnabled();
    const isTopmostTapTarget = await button.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return Boolean(hit && (hit === element || element.contains(hit)));
    });
    expect(isTopmostTapTarget).toBe(true);

    const accepted = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === "/api/data/upload" && response.request().method() === "POST";
    });
    await button.tap();

    await expect(page.getByText("Uploading dataset", { exact: true })).toBeVisible();
    await expect(page.locator("form.intake-flow")).toHaveAttribute("aria-busy", "true");
    await expect(page.locator(".upload-fingerprint-build__nodes b")).toHaveText([
      "Validate", "Map", "Baseline", "Compare", "Evidence",
    ]);
    await expect(page.getByRole("button", { name: "Start Baseline Analysis" })).toHaveCount(0);

    const response = await accepted;
    expect(response.ok()).toBe(true);
    expect(uploadRequests).toBe(1);
    await expect(page.locator("body")).not.toContainText("We hit a workspace error");
  });
});
