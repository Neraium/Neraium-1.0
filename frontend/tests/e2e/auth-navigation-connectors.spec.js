import { expect, test } from "./fixtures.js";
import path from "node:path";

const apiBaseURL = `http://127.0.0.1:${Number(process.env.PLAYWRIGHT_BACKEND_PORT || 8012)}`;
const e2eDatabaseURL = `sqlite:///${path.resolve(process.cwd(), "../.playwright-runtime/e2e-telemetry.sqlite").replaceAll("\\", "/")}`;

async function signIn(page, email = "e2e-admin@neraium.test", password = "e2e-password-123") {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("main", { name: "Neraium platform workspace" })).toBeVisible();
}

test.describe("Authentication, navigation, connectors, and permissions", () => {
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

  test("direct links, refresh, back, and forward preserve a sensible section", async ({ page }) => {
    await page.goto("/workspace?section=systems");
    await expect(page.getByRole("button", { name: /Systems/ }).first()).toHaveAttribute("aria-current", "page");
    await page.reload();
    await expect(page.getByRole("button", { name: /Systems/ }).first()).toHaveAttribute("aria-current", "page");

    await page.getByRole("button", { name: /Datasets & Connectors/ }).first().click();
    await expect(page).toHaveURL(/section=data-sources/);
    await page.goBack();
    await expect(page.getByRole("button", { name: /Systems/ }).first()).toHaveAttribute("aria-current", "page");
    await page.goForward();
    await expect(page.getByRole("button", { name: /Datasets & Connectors/ }).first()).toHaveAttribute("aria-current", "page");
  });

  test("an expired server session returns the user to sign in", async ({ page, context }) => {
    await page.goto("/workspace");
    await expect(page.getByRole("main", { name: "Neraium platform workspace" })).toBeVisible();
    const administrationButton = page.getByRole("button", { name: "Administration" });
    await expect(administrationButton).toBeVisible();
    const logout = await context.request.post(`${apiBaseURL}/api/auth/logout`);
    expect(logout.ok()).toBeTruthy();
    await administrationButton.click();
    await expect(page.getByTestId("auth-screen")).toBeVisible();
    await expect(page.getByRole("status")).toContainText("session expired");
  });

  test("administrator can test and normalize a sample connector with refreshed health", async ({ page }) => {
    await page.goto("/workspace/data-sources");
    await expect(page.getByRole("heading", { name: "Telemetry connector setup" })).toBeVisible();
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

    await page.getByRole("button", { name: "Back to Command Center" }).first().click();
    await page.getByRole("button", { name: "Sign out" }).click();
    await signIn(page, email, "operator-password-123");
    await page.goto("/workspace/admin");
    await expect(page.getByText("Administrator access required")).toBeVisible();
  });
});
