#!/usr/bin/env node

const DEFAULT_BASE_URL = "https://app.neraium.com";
const BASE_URL = (process.env.BASE_URL || DEFAULT_BASE_URL).replace(/\/$/, "");
const TOKEN = process.env.NERAIUM_API_TOKEN || process.env.API_TOKEN || "";
const UPLOAD_TIMEOUT_MS = Number(process.env.SMOKE_UPLOAD_TIMEOUT_MS || 45000);
const POLL_INTERVAL_MS = Number(process.env.SMOKE_POLL_INTERVAL_MS || 1000);

const endpoints = [
  { name: "health", path: "/api/health", required: true },
  { name: "ready", path: "/api/ready", required: true },
  { name: "runner_status", path: "/api/intelligence/runner-status", required: true },
  { name: "metrics", path: "/api/observability/metrics", required: false },
];

function snippet(text) {
  return String(text || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 260);
}

function isHtml(contentType, body) {
  return contentType.toLowerCase().includes("text/html") || /^\s*<!doctype html/i.test(body) || /^\s*<html/i.test(body);
}

function maybeJson(contentType, body) {
  if (!contentType.toLowerCase().includes("application/json")) {
    return null;
  }
  try {
    return JSON.parse(body);
  } catch {
    return null;
  }
}

function authHeaders(accept = "application/json,*/*") {
  const headers = { Accept: accept };
  if (TOKEN) {
    headers.Authorization = `Bearer ${TOKEN}`;
  }
  return headers;
}

function toAbsoluteUrl(path) {
  return /^https?:\/\//i.test(path) ? path : `${BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

function asEpochMillis(value) {
  if (!value) {
    return null;
  }
  const epoch = Date.parse(value);
  return Number.isNaN(epoch) ? null : epoch;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function buildSmokeCsv() {
  const base = Date.now();
  const rows = Array.from({ length: 8 }, (_, index) => {
    const timestamp = new Date(base + index * 60000).toISOString();
    const temperature = (74.5 + index * 0.4).toFixed(1);
    const humidity = (56 + index * 0.5).toFixed(1);
    return `${timestamp},Smoke Room,${temperature},${humidity}`;
  });
  return `timestamp,room,temperature,humidity\n${rows.join("\n")}\n`;
}

async function probe(endpoint) {
  const headers = authHeaders(endpoint.name === "metrics" ? "text/plain,*/*" : "application/json,*/*");
  const url = toAbsoluteUrl(endpoint.path);
  const started = Date.now();
  let response;
  let body = "";
  try {
    response = await fetch(url, { headers, signal: AbortSignal.timeout(15000) });
    body = await response.text();
  } catch (error) {
    return {
      endpoint,
      ok: false,
      status: "FETCH_ERROR",
      contentType: "",
      durationMs: Date.now() - started,
      body: error?.message || String(error),
      hardFail: endpoint.required,
    };
  }

  const contentType = response.headers.get("content-type") || "";
  const html = isHtml(contentType, body);
  const authBlockedMetrics = endpoint.name === "metrics" && (response.status === 401 || response.status === 403);
  const ok = response.ok && !html;
  return {
    endpoint,
    ok: ok || authBlockedMetrics,
    status: response.status,
    contentType,
    durationMs: Date.now() - started,
    body,
    json: maybeJson(contentType, body),
    hardFail: endpoint.required && (!response.ok || html),
    warning: authBlockedMetrics ? "metrics requires auth" : html ? "HTML error page detected" : "",
  };
}

async function fetchJson(path, { timeoutMs = 15000 } = {}) {
  const url = toAbsoluteUrl(path);
  const response = await fetch(url, {
    headers: authHeaders(),
    signal: AbortSignal.timeout(timeoutMs),
  });
  const body = await response.text();
  const contentType = response.headers.get("content-type") || "";
  const json = maybeJson(contentType, body);
  return { url, response, body, json, contentType };
}

async function uploadSmokeTelemetry() {
  const filename = `smoke-production-${Date.now()}.csv`;
  const form = new FormData();
  form.set("file", new Blob([buildSmokeCsv()], { type: "text/csv" }), filename);
  const response = await fetch(toAbsoluteUrl("/api/data/upload"), {
    method: "POST",
    headers: {
      ...authHeaders("*/*"),
      "X-Neraium-User": "production-smoke",
    },
    body: form,
    signal: AbortSignal.timeout(15000),
  });
  const body = await response.text();
  const contentType = response.headers.get("content-type") || "";
  const json = maybeJson(contentType, body);
  return { response, body, json, filename };
}

async function pollUploadStatus(statusUrl, { timeoutMs = UPLOAD_TIMEOUT_MS } = {}) {
  const deadline = Date.now() + timeoutMs;
  let lastPayload = null;
  let lastStatusCode = null;
  while (Date.now() < deadline) {
    const result = await fetchJson(statusUrl, { timeoutMs: 15000 });
    lastStatusCode = result.response.status;
    lastPayload = result.json;
    if (result.response.ok && lastPayload && ["COMPLETE", "FAILED"].includes(lastPayload.status)) {
      return lastPayload;
    }
    await sleep(POLL_INTERVAL_MS);
  }
  const summary = lastPayload ? JSON.stringify(lastPayload) : `status_code=${lastStatusCode}`;
  throw new Error(`Upload did not reach a terminal state within ${timeoutMs}ms. last=${summary}`);
}

if (typeof fetch !== "function") {
  console.error("Node fetch is unavailable. Use Node 18 or newer.");
  process.exit(2);
}

console.log(`Neraium production smoke test`);
console.log(`BASE_URL=${BASE_URL}`);

const results = [];
const resultByName = new Map();
for (const endpoint of endpoints) {
  const result = await probe(endpoint);
  results.push(result);
  resultByName.set(endpoint.name, result);
  const marker = result.ok ? "PASS" : result.hardFail ? "FAIL" : "WARN";
  console.log(`\n[${marker}] ${endpoint.name} ${endpoint.path}`);
  console.log(`status=${result.status} content-type=${result.contentType || "n/a"} duration_ms=${result.durationMs}`);
  if (result.warning) {
    console.log(`warning=${result.warning}`);
  }
  console.log(`snippet=${snippet(result.body) || "<empty>"}`);
}

const failed = results.filter((result) => result.hardFail);
if (failed.length) {
  console.error(`\nSmoke test failed: ${failed.map((result) => result.endpoint.name).join(", ")}`);
  process.exit(1);
}

let uploadPhaseFailed = false;
const beforeRunnerStatus = resultByName.get("runner_status")?.json || {};
const beforeProcessedAt = beforeRunnerStatus.last_processed_at || null;
const uploadStartedAt = new Date().toISOString();
console.log(`\n[STEP] upload smoke telemetry batch`);

try {
  const upload = await uploadSmokeTelemetry();
  const uploadOk = upload.response.ok && upload.json && upload.json.job_id && upload.json.status_url;
  console.log(`status=${upload.response.status} filename=${upload.filename}`);
  console.log(`snippet=${snippet(upload.body) || "<empty>"}`);
  if (!uploadOk) {
    throw new Error(`Upload was not accepted. body=${snippet(upload.body) || "<empty>"}`);
  }

  const terminal = await pollUploadStatus(upload.json.status_url);
  console.log(`terminal_status=${terminal.status} job_id=${terminal.job_id} runner_used=${terminal.runner_used}`);

  const latestUpload = await fetchJson("/api/data/latest-upload");
  const latestPayload = latestUpload.json || {};
  const afterRunner = await fetchJson("/api/intelligence/runner-status");
  const runnerPayload = afterRunner.json || {};
  const uploadIssues = [];

  if (terminal.status !== "COMPLETE") {
    uploadIssues.push(`upload finished with ${terminal.status}`);
  }
  if (!terminal.runner_used) {
    uploadIssues.push("upload completed without SII runner");
  }
  if (latestUpload.response.status !== 200) {
    uploadIssues.push(`/api/data/latest-upload returned ${latestUpload.response.status}`);
  }
  if (afterRunner.response.status !== 200) {
    uploadIssues.push(`/api/intelligence/runner-status returned ${afterRunner.response.status}`);
  }
  if (latestPayload.last_filename !== upload.filename) {
    uploadIssues.push(`latest upload filename did not advance to ${upload.filename}`);
  }
  if (latestPayload.state_available !== true) {
    uploadIssues.push("latest upload did not expose visible runtime state");
  }
  if (runnerPayload.state_available !== true) {
    uploadIssues.push("runner status did not report visible runtime state");
  }
  if (!runnerPayload.last_processed_at) {
    uploadIssues.push("runner status did not report last_processed_at");
  }

  const afterProcessedAtMs = asEpochMillis(runnerPayload.last_processed_at);
  const beforeProcessedAtMs = asEpochMillis(beforeProcessedAt);
  const uploadStartedAtMs = asEpochMillis(uploadStartedAt);
  if (runnerPayload.last_processed_at && afterProcessedAtMs === null) {
    uploadIssues.push("runner status returned an invalid last_processed_at timestamp");
  }
  if (beforeProcessedAtMs !== null && afterProcessedAtMs !== null && afterProcessedAtMs <= beforeProcessedAtMs) {
    uploadIssues.push("runner last_processed_at did not move forward after the smoke upload");
  }
  if (uploadStartedAtMs !== null && afterProcessedAtMs !== null && afterProcessedAtMs < uploadStartedAtMs) {
    uploadIssues.push("runner state is older than the smoke upload start time");
  }

  console.log(`latest_upload_last_filename=${latestPayload.last_filename || "n/a"} state_available=${latestPayload.state_available}`);
  console.log(`runner_last_processed_at=${runnerPayload.last_processed_at || "n/a"} state_age_seconds=${runnerPayload.state_age_seconds ?? "n/a"}`);

  if (uploadIssues.length) {
    uploadPhaseFailed = true;
    console.error(`upload_smoke_failures=${uploadIssues.join("; ")}`);
  } else {
    console.log("upload smoke passed.");
  }
} catch (error) {
  uploadPhaseFailed = true;
  console.error(`upload_smoke_error=${error?.message || String(error)}`);
}

if (uploadPhaseFailed) {
  console.error("\nSmoke test failed after basic API health passed. This would have been a false green before the split-ECS worker smoke step.");
  process.exit(1);
}

console.log("\nSmoke test passed, including worker/SII smoke upload.");
