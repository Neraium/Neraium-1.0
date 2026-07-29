export async function installStoredBaselineUpload(page, {
  jobId = "e2e-baseline-job",
  completeWhenPolled = false,
  objectDelayMs = 0,
} = {}) {
  const calls = { sessions: 0, objectPuts: 0, completions: 0, statusPolls: 0, baselineResults: 0 };
  const statusUrl = `/api/data/upload-status/${jobId}`;
  const baselineResultUrl = `/api/data/baselines/jobs/${jobId}`;
  const processing = {
    job_id: jobId,
    upload_session_id: jobId,
    status: "PROCESSING",
    processing_state: "validating",
    worker_state: "active",
    percent: 35,
    progress: 35,
    progress_label: "Validating historical data",
    result_available: false,
    workflow: "create_baseline",
    status_url: statusUrl,
    baseline_result_url: baselineResultUrl,
  };
  const complete = {
    ...processing,
    status: "COMPLETE",
    processing_state: "complete",
    percent: 100,
    progress: 100,
    progress_label: "Initial baseline established",
    result_available: true,
  };
  const baselineResult = {
    job_id: jobId,
    dataset_id: jobId,
    workflow: "create_baseline",
    candidate_model: {
      model_id: `${jobId}-model`,
      version: 1,
      status: "active",
      activation: { state: "active", activated_at: "2026-07-29T00:00:00Z" },
      signal_memory: { signal_count: 5 },
      relationship_memory: { relationship_count: 4 },
    },
    activation: { state: "active", activated_at: "2026-07-29T00:00:00Z" },
    data_quality: { rows_accepted: 48, coverage_percent: 100 },
  };
  const uploadUrl = `https://upload.example.test/${jobId}`;

  await page.route("**/api/data/upload-session", (route) => {
    calls.sessions += 1;
    return route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        upload_session_id: jobId,
        upload_url: uploadUrl,
        upload_headers: { "Content-Type": "text/csv" },
        upload_method: "PUT",
        workflow: "create_baseline",
      }),
    });
  });
  await page.route(uploadUrl, async (route) => {
    calls.objectPuts += 1;
    if (objectDelayMs > 0) await new Promise((resolve) => setTimeout(resolve, objectDelayMs));
    return route.fulfill({ status: 200, headers: { etag: `"${jobId}-etag"` }, body: "" });
  });
  await page.route(`**/api/data/upload-session/${jobId}/complete`, (route) => {
    calls.completions += 1;
    return route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(processing) });
  });
  await page.route(`**${statusUrl}`, (route) => {
    calls.statusPolls += 1;
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(completeWhenPolled ? complete : processing) });
  });
  await page.route(`**${baselineResultUrl}`, (route) => {
    calls.baselineResults += 1;
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(baselineResult) });
  });

  return calls;
}
