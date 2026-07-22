import { expect, test } from "./fixtures.js";
import path from "node:path";

const apiBaseURL = `http://127.0.0.1:${Number(process.env.PLAYWRIGHT_BACKEND_PORT || 8012)}`;
const e2eDatabaseURL = `sqlite:///${path.resolve(process.cwd(), "../.playwright-runtime/e2e-telemetry.sqlite").replaceAll("\\", "/")}`;

const AUTH_VIEWPORTS = [
  { name: "iPhone 12/13", width: 390, height: 844 },
  { name: "iPhone 14/15 Pro Max", width: 430, height: 932 },
];

async function expectCompactAuthLayout(page, viewport) {
  await page.setViewportSize({ width: viewport.width, height: viewport.height });
  await page.goto("/workspace", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("auth-screen")).toBeVisible();
  await expect(page.getByText("Systemic Infrastructure Intelligence")).toBeVisible();
  await expect(page.getByText(/See the behavior behind the system/i)).toHaveCount(0);
  await expect(page.getByText(/decision environment/i)).toHaveCount(0);
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByLabel("Password")).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();

  const metrics = await page.evaluate(() => {
    const root = document.documentElement;
    const body = document.body;
    const rectFor = (selector) => {
      const node = document.querySelector(selector);
      if (!node) return null;
      const rect = node.getBoundingClientRect();
      return { top: rect.top, bottom: rect.bottom, left: rect.left, right: rect.right, width: rect.width };
    };

    return {
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      scrollWidth: root.scrollWidth,
      bodyScrollWidth: body.scrollWidth,
      email: rectFor("#auth-email"),
      password: rectFor("#auth-password"),
      button: rectFor(".auth-submit"),
    };
  });

  expect(metrics.scrollWidth, `${viewport.name} document width`).toBeLessThanOrEqual(metrics.viewportWidth + 1);
  expect(metrics.bodyScrollWidth, `${viewport.name} body width`).toBeLessThanOrEqual(metrics.viewportWidth + 1);
  expect(metrics.email?.left, `${viewport.name} email left`).toBeGreaterThanOrEqual(0);
  expect(metrics.email?.right, `${viewport.name} email right`).toBeLessThanOrEqual(metrics.viewportWidth + 1);
  expect(metrics.password?.bottom, `${viewport.name} password bottom`).toBeLessThanOrEqual(metrics.viewportHeight + 1);
  expect(metrics.button?.bottom, `${viewport.name} sign-in button bottom`).toBeLessThanOrEqual(metrics.viewportHeight + 1);
}

async function signIn(page, email = "e2e-admin@neraium.test", password = "e2e-password-123") {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("main", { name: "Neraium platform workspace" })).toBeVisible();
}

test.describe("Authentication, navigation, connectors, and permissions", () => {
  test("compact sign-in screen keeps primary controls in initial iPhone viewports", async ({ page, context }) => {
    for (const viewport of AUTH_VIEWPORTS) {
      const logout = await context.request.post(`${apiBaseURL}/api/auth/logout`);
      expect(logout.ok(), viewport.name).toBeTruthy();
      await expectCompactAuthLayout(page, viewport);
    }
  });

  test("sign out, failed sign in, and sign in provide actionable feedback", async ({ page }) => {
    await page.goto("/workspace");
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByTestId("auth-screen")).toBeVisible();
    await expect(page.getByRole("status")).toContainText("signed out");

    await page.getByLabel("Email").fill("e2e-admin@neraium.test");
    await page.getByLabel("Password").fill("wrong-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("alert")).toContainText("Invalid email or password");

    await signIn(page);
  });

  test("direct links, refresh, back, and forward preserve engineering workspaces", async ({ page }) => {
    await page.goto("/sites/current");
    await expect(page.getByRole("button", { name: "Site Overview" })).toHaveAttribute("aria-current", "page");
    await page.reload();
    await expect(page.getByRole("button", { name: "Site Overview" })).toHaveAttribute("aria-current", "page");

    await page.getByRole("button", { name: "Portfolio" }).click();
    await expect(page).toHaveURL(/\/portfolio$/);
    await page.goBack();
    await expect(page.getByRole("button", { name: "Site Overview" })).toHaveAttribute("aria-current", "page");
    await page.goForward();
    await expect(page.getByRole("button", { name: "Portfolio" })).toHaveAttribute("aria-current", "page");
  });

  test("an expired server session returns the user to sign in", async ({ page, context }) => {
    await page.goto("/workspace");
    await expect(page.getByRole("main", { name: "Neraium platform workspace" })).toBeVisible();
    const administrationButton = page.getByRole("button", { name: "Governance / Administration" });
    await expect(administrationButton).toBeVisible();
    await page.route("**/api/observability/evp-governance*", (route) => route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Session expired." }),
    }));
    await administrationButton.click();
    await expect(page.getByTestId("auth-screen")).toBeVisible();
    await expect(page.getByRole("status")).toContainText("session expired");
  });

  test("administrator can test and normalize a sample connector with refreshed health", async ({ page }) => {
    await page.goto("/workspace/data-sources");
    await expect(page.getByRole("heading", { name: /Telemetry connector setup/i })).toHaveCount(0);

    await page.goto("/workspace/admin");
    await expect(page.getByRole("heading", { name: /Telemetry connector setup/i })).toBeVisible();
    await page.getByLabel("Connector type").selectOption("database");
    await page.getByLabel("Database URL").fill(e2eDatabaseURL);
    await page.getByRole("button", { name: "Test connection" }).click();
    await expect(page.getByRole("status")).toContainText("No records were saved");
    await page.getByRole("button", { name: "Prepare sample" }).click();
    await expect(page.getByRole("status")).toContainText("records were validated for analysis");
    await expect(page.getByLabel("Connector health")).toContainText("2 records");
    await expect(page.getByLabel("Connector health")).not.toContainText("must be numeric");
  });

  test("administrator creates an operator whose direct admin link is denied in the frontend", async ({ page }) => {
    const email = `operator-${Date.now()}@neraium.test`;
    await page.goto("/workspace/admin");
    await expect(page.getByText("User Access", { exact: true })).toBeVisible();
    await page.getByLabel("User email").fill(email);
    await page.getByLabel("User name").fill("Workflow Operator");
    await page.getByLabel("Temporary password").fill("operator-password-123");
    await page.getByLabel("User role").selectOption("operator");
    await page.getByRole("button", { name: "Create Account" }).click();
    await expect(page.getByText(email)).toBeVisible();

    await page.getByRole("button", { name: "Back to Portfolio" }).first().click();
    await page.getByRole("button", { name: "Sign out" }).click();
    await signIn(page, email, "operator-password-123");
    await page.goto("/workspace/admin");
    await expect(page.getByText("Administrator access required")).toBeVisible();
  });
});
