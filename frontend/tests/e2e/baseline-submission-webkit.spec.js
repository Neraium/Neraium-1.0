import { expect, test } from "./fixtures.js";
import { installStoredBaselineUpload } from "./stored-upload-mock.js";

test.describe("mobile Safari baseline submission", () => {
  test.use({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });

  test("the baseline button is the topmost tap target and immediately starts the stored upload", async ({ page }) => {
    const calls = await installStoredBaselineUpload(page, { jobId: "mobile-safari", objectDelayMs: 750 });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("app-ready-root")).toHaveAttribute("data-app-ready", "1");
    await page.getByRole("button", { name: "Import Historical Dataset", exact: true }).tap();
    await expect(page.getByRole("heading", { name: "Establish Initial Baseline", level: 2 })).toBeVisible();

    await page.getByTestId("csv-upload-input").setInputFiles({
      name: "mobile-safari.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(
        "timestamp,room,temperature,humidity\n2026-05-01T08:00:00Z,Plant,75.2,58\n2026-05-01T08:05:00Z,Plant,75.5,59\n",
        "utf8",
      ),
    });

    const button = page.getByRole("button", { name: "Continue" });
    await expect(button).toBeEnabled();
    const isTopmostTapTarget = await button.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return Boolean(hit && (hit === element || element.contains(hit)));
    });
    expect(isTopmostTapTarget).toBe(true);

    await button.tap();
    const progress = page.getByRole("progressbar", { name: /Upload, stage 1 of 4/ });
    await expect(progress).toBeVisible();
    await expect(page.locator("form.intake-flow")).toHaveAttribute("aria-busy", "true");
    await expect(progress.getByRole("listitem")).toHaveText([
      "1UploadSecurely transferring historical operating data.",
      "2ValidateVerifying dataset integrity, timestamps, signal consistency, and data quality.",
      "3LearnLearning how the infrastructure normally behaves by identifying persistent operating relationships across the dataset.",
      "4Baseline ReadyInitial operating model successfully established.",
    ]);
    await expect(page.getByRole("button", { name: "Continue" })).toHaveCount(0);
    await expect.poll(() => calls.completions).toBe(1);
    expect(calls.sessions).toBe(1);
    expect(calls.objectPuts).toBe(1);
    await expect(page.locator("body")).not.toContainText("We hit a workspace error");
  });
});
