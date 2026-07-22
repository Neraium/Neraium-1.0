import { expect, test as base } from "@playwright/test";

const apiBaseURL = `http://127.0.0.1:${Number(process.env.PLAYWRIGHT_BACKEND_PORT || 8012)}`;

export const test = base.extend({
  page: async ({ page, context }, use) => {
    const login = await context.request.post(`${apiBaseURL}/api/auth/login`, {
      data: { email: "e2e-admin@neraium.test", password: "e2e-password-123" },
    });
    if (!login.ok()) throw new Error(`E2E sign in failed with ${login.status()}`);
    const loginPayload = await login.json();
    const sessionId = String(loginPayload?.session?.session_id ?? "");
    if (!sessionId) throw new Error("E2E sign in did not return a session id");
    // The E2E server is production-configured but runs on loopback HTTP. Mirror
    // the issued HttpOnly session as non-secure only inside this local context.
    await context.addCookies([{
      name: "neraium_session",
      value: sessionId,
      url: apiBaseURL,
      httpOnly: true,
      secure: false,
      sameSite: "Lax",
    }]);
    const reset = await context.request.post(`${apiBaseURL}/api/data/reset`);
    if (!reset.ok()) throw new Error(`E2E state reset failed with ${reset.status()}`);
    await use(page);
  },
});

export { expect };
