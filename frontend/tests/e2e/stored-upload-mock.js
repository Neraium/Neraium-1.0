export async function installStoredBaselineUpload(page, {
  jobId = "e2e-baseline-job",
  completeWhenPolled = false,
  objectDelayMs = 0,
  modelId = `${jobId}-model`,
  portfolioId = "default",
  filename = `${jobId}.csv`,
  staleLatestResult = null,
  ingestionTrust = null,
  processingOverrides = {},
  latestWhileProcessing = false,
} = {}) {
  const calls = { sessions: 0, objectPuts: 0, completions: 0, statusPolls: 0, baselineResults: 0, exactBaselineResults: 0, latestUploads: 0 };
  let completionAvailable = false;
  const statusUrl = `/api/data/upload-status/${jobId}`;
  const baselineResultUrl = `/api/data/baselines/jobs/${jobId}`;
  const exactBaselineResultUrl = `/api/data/portfolios/${portfolioId}/baselines/${modelId}`;
  const createdAt = "2026-07-30T00:00:00Z";
  const workspacePath = `/baselines/${modelId}/ready`;
  const processingProgress = {
    contract_version: "job-progress.v1",
    job_id: jobId,
    workflow: "create_baseline",
    status: "processing",
    stage: "validate",
    substage: "signal_inventory",
    completed_units: 6,
    total_units: 10,
    percent_complete: 60,
    unit_type: "signals",
    message: "Inventoried 6 of 10 candidate signals.",
    started_at: "2026-07-30T00:00:00Z",
    updated_at: "2026-07-30T00:00:12Z",
    elapsed_seconds: 12,
    last_worker_heartbeat_at: "2026-07-30T00:00:12Z",
    seconds_since_worker_heartbeat: 0,
    seconds_since_update: 0,
    stalled: false,
    retryable: null,
    error: null,
    metadata: {},
    workflow_steps: [
      { id: "upload", label: "Upload", status: "completed", completed_work_units: 2, total_work_units: 2, percent_complete: 100 },
      { id: "validate", label: "Validate", status: "processing", completed_work_units: 4, total_work_units: 13, percent_complete: 35 },
      { id: "learn", label: "Learn", status: "pending", completed_work_units: 0, total_work_units: 6, percent_complete: 0 },
      { id: "ready", label: "Baseline Ready", status: "pending", completed_work_units: 0, total_work_units: 1, percent_complete: 0 },
    ],
    operations: [
      { id: "receiving", stage: "upload", label: "Receiving file", status: "completed", percent_complete: 100 },
      { id: "parse_source", stage: "validate", label: "Parse source", status: "completed", percent_complete: 100 },
      { id: "timestamp_quality", stage: "validate", label: "Timestamp quality", status: "completed", percent_complete: 100 },
      { id: "signal_inventory", stage: "validate", label: "Signal inventory", status: "processing", completed_units: 6, total_units: 10, percent_complete: 60 },
      { id: "semantic_mapping", stage: "validate", label: "Semantic mapping", status: "pending", percent_complete: null },
      { id: "unit_normalization", stage: "validate", label: "Unit normalization", status: "pending", percent_complete: null },
      { id: "learn_relationships", stage: "learn", label: "Learn relationships", status: "pending", percent_complete: null },
    ],
    overall_percent_complete: 30,
    overall_basis: "equal_completed_declared_substages",
  };
  const processing = {
    job_id: jobId,
    jobId,
    dataset_id: jobId,
    datasetId: jobId,
    upload_session_id: jobId,
    status: "PROCESSING",
    processing_state: "validating",
    worker_state: "running",
    execution_state: "processing",
    percent: 35,
    progress: 35,
    progress_label: "Validating historical data",
    job_progress: processingProgress,
    result_available: false,
    workflow: "create_baseline",
    filename,
    ...(ingestionTrust ? { ingestion_trust: ingestionTrust } : {}),
    status_url: statusUrl,
    baseline_result_url: baselineResultUrl,
    ...processingOverrides,
  };
  const complete = {
    ...processing,
    status: "COMPLETE",
    processing_state: "complete",
    percent: 100,
    progress: 100,
    progress_label: "Initial baseline established",
    result_available: true,
    baseline_result_available: true,
    job_state: "completed",
    execution_state: "completed",
    job_progress: {
      ...processingProgress,
      status: "completed",
      stage: "ready",
      substage: "finalize_baseline",
      completed_units: 1,
      total_units: 1,
      percent_complete: 100,
      unit_type: "operation",
      message: "Behavioral baseline candidate ready.",
      elapsed_seconds: 24,
      workflow_steps: processingProgress.workflow_steps.map((step) => ({ ...step, status: "completed", completed_work_units: step.total_work_units, percent_complete: 100 })),
      operations: processingProgress.operations.map((operation) => ({ ...operation, status: "completed", percent_complete: 100 })),
      overall_percent_complete: 100,
    },
    baselineId: modelId,
    portfolioId,
    systemId: portfolioId,
    workspacePath,
    createdAt,
  };
  const baselineResult = {
    status: "COMPLETE",
    processing_state: "complete",
    job_id: jobId,
    jobId,
    upload_id: jobId,
    dataset_id: jobId,
    datasetId: jobId,
    baselineId: modelId,
    portfolioId,
    systemId: portfolioId,
    workspacePath,
    createdAt,
    completed_at: createdAt,
    baseline_candidate_id: modelId,
    established_baseline_id: modelId,
    portfolio_id: portfolioId,
    system_id: portfolioId,
    filename,
    workflow: "create_baseline",
    ...(ingestionTrust ? { ingestion_trust: ingestionTrust } : {}),
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
    if (latestWhileProcessing && !completeWhenPolled) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...processing,
          session_state: String(processing.execution_state || processing.processing_state || "processing").toLowerCase(),
          latest_result: null,
          current_upload: processing,
          history: [],
        }),
      });
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
