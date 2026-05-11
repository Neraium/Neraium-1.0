#!/usr/bin/env node

const DEFAULT_BASE_URL = "https://app.neraium.com";
const BASE_URL = (process.env.BASE_URL || DEFAULT_BASE_URL).replace(/\/$/, "");
const TOKEN = process.env.NERAIUM_API_TOKEN || process.env.API_TOKEN || "";

const endpoints = [
  { name: "health", path: "/api/health", required: true },
  { name: "ready", path: "/api/ready", required: true },
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

async function probe(endpoint) {
  const headers = { Accept: endpoint.name === "metrics" ? "text/plain,*/*" : "application/json,*/*" };
  if (TOKEN) {
    headers.Authorization = `Bearer ${TOKEN}`;
  }
  const url = `${BASE_URL}${endpoint.path}`;
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
    hardFail: endpoint.required && (!response.ok || html),
    warning: authBlockedMetrics ? "metrics requires auth" : html ? "HTML error page detected" : "",
  };
}

if (typeof fetch !== "function") {
  console.error("Node fetch is unavailable. Use Node 18 or newer.");
  process.exit(2);
}

console.log(`Neraium production smoke test`);
console.log(`BASE_URL=${BASE_URL}`);

const results = [];
for (const endpoint of endpoints) {
  const result = await probe(endpoint);
  results.push(result);
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

console.log("\nSmoke test passed for required endpoints.");
