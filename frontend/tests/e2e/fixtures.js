import { expect, test as base } from "@playwright/test";

const apiBaseURL = `http://127.0.0.1:${Number(process.env.PLAYWRIGHT_BACKEND_PORT || 8012)}`;

export function governedComparisonResult(result) {
  const runId = String(result?.job_id ?? "e2e-comparison-run");
  const baselineId = `${runId}-baseline`;
  const baselineDatasetId = `${runId}-baseline-dataset`;
  const comparisonDatasetId = `${runId}-comparison-dataset`;
  return {
    ...result,
    job_id: runId,
    run_id: runId,
    workflow: "analyze_new_data",
    status: "COMPLETE",
    processing_state: "complete",
    sii_completed: true,
    portfolio_id: "default",
    system_id: "default",
    baseline_id: baselineId,
    baseline_dataset_id: baselineDatasetId,
    comparison_dataset_id: comparisonDatasetId,
    comparison_analysis_id: runId,
    analysis_run_id: runId,
    dataset_id: comparisonDatasetId,
    active_baseline_reference: { model_id: baselineId, dataset_id: baselineDatasetId },
  };
}

export const test = base.extend({
  page: async ({ page, context }, use) => {
    const login = await context.request.post(`${apiBaseURL}/api/auth/login`, {
      data: { email: "e2e-admin@neraium.test", password: "e2e-password-123" },
    });
    if (!login.ok()) throw new Error(`E2E sign in failed with ${login.status()}`);
    const sessionCookie = (await context.cookies()).find((cookie) =>
      cookie.name === "neraium_session" && cookie.domain === new URL(apiBaseURL).hostname);
    if (!sessionCookie?.value) throw new Error("E2E sign in did not issue a session cookie");
    // The JSON session_id is a public management handle, not a bearer credential.
    // Preserve the issued cookie, adapting Secure only for this loopback HTTP context.
    await context.addCookies([{
      ...sessionCookie,
      secure: false,
    }]);
    const reset = await context.request.post(`${apiBaseURL}/api/data/reset`);
    if (!reset.ok()) throw new Error(`E2E state reset failed with ${reset.status()}`);
    await use(page);
  },
});

export { expect };
