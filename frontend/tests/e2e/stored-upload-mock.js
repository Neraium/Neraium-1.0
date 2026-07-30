export async function installStoredBaselineUpload(page, {
  jobId = "e2e-baseline-job",
  completeWhenPolled = false,
  objectDelayMs = 0,
  modelId = `${jobId}-model`,
  portfolioId = "default",
  filename = `${jobId}.csv`,
  staleLatestResult = null,
} = {}) {
  const calls = { sessions: 0, objectPuts: 0, completions: 0, statusPolls: 0, baselineResults: 0, exactBaselineResults: 0, latestUploads: 0 };
  let completionAvailable = false;
  const statusUrl = `/api/data/upload-status/${jobId}`;
  const baselineResultUrl = `/api/data/baselines/jobs/${jobId}`;
  const exactBaselineResultUrl = `/api/data/portfolios/${portfolioId}/baselines/${modelId}`;
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
    upload_id: jobId,
    dataset_id: jobId,
    baseline_candidate_id: modelId,
    established_baseline_id: modelId,
    portfolio_id: portfolioId,
    system_id: portfolioId,
    filename,
    workflow: "create_baseline",
    candidate_model: {
      model_id: modelId,
      baseline_id: modelId,
      version: 1,
      status: "active",
      activation: { state: "active", activated_at: "2026-07-29T00:00:00Z" },
      signal_memory: { signal_count: 5 },
      relationship_memory: { relationship_count: 4 },
      telemetry_schema: { numeric_columns: ["flow_gpm", "pressure_psi", "pump_speed_pct"] },
      relationship_graph: { edges: [{ edge_id: "edge-1", source: "flow_gpm", target: "pressure_psi", strength: 0.82, sample_count: 48 }] },
      operating_modes: [{ mode_id: "mode-1", label: "normal load", sample_count: 48, sample_fraction: 1 }],
      data_quality: { readiness: "ready", reliability_rating: "high", reliability_score: 0.98, timestamp_detected: true },
      timestamp_quality: { first_timestamp: "2026-07-28T00:00:00Z", last_timestamp: "2026-07-29T00:00:00Z", estimated_sample_interval: "5 minutes" },
      source: { job_id: jobId, dataset_id: jobId, filename, portfolio_id: portfolioId, system_id: portfolioId, row_count: 48 },
    },
    analysis_state: { status: "empty", count: 0, analyses: [] },
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
    return route.fulfill({ status: 200, headers: { etag: `"${jobId}-etag"`, "access-control-allow-origin": "*", "access-control-expose-headers": "etag" }, body: "" });
  });
  await page.route(`**/api/data/upload-session/${jobId}/complete`, (route) => {
    calls.completions += 1;
    completionAvailable = true;
    return route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(processing) });
  });
  await page.route(`**${statusUrl}`, (route) => {
    calls.statusPolls += 1;
    if (completeWhenPolled) completionAvailable = true;
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(completeWhenPolled ? complete : processing) });
  });
  await page.route("**/api/data/latest-upload?*", (route) => {
    calls.latestUploads += 1;
    if (staleLatestResult) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "COMPLETE",
          processing_state: "complete",
          session_state: "restored",
          latest_result: staleLatestResult,
          current_upload: { job_id: staleLatestResult.job_id, status: "COMPLETE", result: staleLatestResult },
          history: [],
        }),
      });
    }
    if (!completionAvailable) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "empty", session_state: "empty", history: [] }) });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...complete,
        session_state: "restored",
        latest_result: baselineResult,
        current_upload: { job_id: jobId, upload_id: jobId, dataset_id: jobId, status: "COMPLETE", result: baselineResult },
        history: [],
      }),
    });
  });
  await page.route(`**${baselineResultUrl}`, (route) => {
    calls.baselineResults += 1;
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(baselineResult) });
  });
  await page.route(`**${exactBaselineResultUrl}`, (route) => {
    calls.exactBaselineResults += 1;
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(baselineResult) });
  });

  return calls;
}
