import { getCurrentWorkspaceId } from "./services/datasetSessionCache";

const STALE_API_HOST = ["api", "neraium", "com"].join(".");

function normalizeConfiguredApiBaseUrl(value = "") {
  const normalized = String(value ?? "").trim().replace(/\/+$/, "");
  if (!normalized) return "";

  try {
    const url = new URL(normalized);
    return url.hostname === STALE_API_HOST ? "" : normalized;
  } catch {
    return normalized;
  }
}

const configuredApiBaseUrl = normalizeConfiguredApiBaseUrl(import.meta.env.VITE_API_BASE_URL);
const isProductionBuild = import.meta.env.PROD;
const configuredApiTimeoutMs = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? "45000");
const API_TIMEOUT_MS = Number.isFinite(configuredApiTimeoutMs) && configuredApiTimeoutMs > 0
  ? configuredApiTimeoutMs
  : 45000;
const WRITE_API_TIMEOUT_MS = Math.max(API_TIMEOUT_MS, 300000);
const productionDefaultApiBaseUrl = configuredApiBaseUrl || (isProductionBuild ? "" : "http://127.0.0.1:8010");

export const API_BASE_URL = productionDefaultApiBaseUrl;
export const CONFIGURED_API_BASE_URL = configuredApiBaseUrl;
export const API_ROUTE_MODE = isProductionBuild ? (configuredApiBaseUrl ? "configured-host" : "same-origin") : (configuredApiBaseUrl ? "configured-host" : "local-backend");

function isCrossOriginApiTarget(apiBaseUrl = API_BASE_URL) {
  if (typeof window === "undefined" || !apiBaseUrl) {
    return false;
  }

  try {
    const target = new URL(apiBaseUrl, window.location.origin);
    return target.origin !== window.location.origin;
  } catch {
    return false;
  }
}

function timeoutMessage(timeoutMs, path) {
  void timeoutMs;
  void path;
  return "The analysis service took too long to respond. Retry the action.";
}

function isPublicReadonlyPath(path) {
  const normalized = String(path || "").toLowerCase();
  return (
    normalized.startsWith("/api/health")
    || normalized.startsWith("/api/domain/mode")
    || normalized.startsWith("/api/intelligence/engine-identity")
  );
}

function normalizeApiPath(path) {
  const input = String(path ?? "").trim();
  if (!input) {
    return "/api/health";
  }
  if (/^https?:\/\//i.test(input)) {
    return input;
  }
  if (input.startsWith("/api/upload-status/")) {
    return input.replace("/api/upload-status/", "/api/data/upload-status/");
  }
  if (input.startsWith("/api/upload-stream/")) {
    return input.replace("/api/upload-stream/", "/api/data/upload-stream/");
  }
  if (input.startsWith("/api/") || input === "/api") {
    return input;
  }
  if (input.startsWith("/latest-upload")) {
    return `/api/data${input}`;
  }
  if (input.startsWith("/upload-status/")) {
    return `/api/data${input}`;
  }
  if (input.startsWith("/replay/")) {
    return `/api/data${input}`;
  }
  if (input.startsWith("/systems")) {
    return `/api/facility${input}`;
  }
  if (input === "/health" || input.startsWith("/health?")) {
    return `/api${input}`;
  }
  if (input === "/mode" || input.startsWith("/mode?")) {
    return `/api/domain${input}`;
  }
  if (input === "/engine-identity" || input.startsWith("/engine-identity?")) {
    return `/api/intelligence${input}`;
  }
  if (input.startsWith("api/upload-status/")) {
    return `/api/data/upload-status/${input.slice("api/upload-status/".length)}`;
  }
  if (input.startsWith("api/upload-stream/")) {
    return `/api/data/upload-stream/${input.slice("api/upload-stream/".length)}`;
  }
  if (input.startsWith("api/")) {
    return `/${input}`;
  }
  if (input.startsWith("/")) {
    return input;
  }
  if (input.startsWith("latest-upload")) {
    return `/api/data/${input}`;
  }
  if (input.startsWith("upload-status/")) {
    return `/api/data/${input}`;
  }
  if (input.startsWith("replay/")) {
    return `/api/data/${input}`;
  }
  if (input.startsWith("systems")) {
    return `/api/facility/${input}`;
  }
  if (input === "health" || input.startsWith("health?")) {
    return `/api/${input}`;
  }
  if (input === "mode" || input.startsWith("mode?")) {
    return `/api/domain/${input}`;
  }
  if (input === "engine-identity" || input.startsWith("engine-identity?")) {
    return `/api/intelligence/${input}`;
  }
  return `/${input}`;
}

function buildUrl(apiBaseUrl, path) {
  const normalizedPath = normalizeApiPath(path);
  return apiBaseUrl ? `${apiBaseUrl}${normalizedPath}` : normalizedPath;
}

function dedupe(values) {
  return [...new Set(values.filter(Boolean))];
}

export function buildApiUrl(path) {
  return buildUrl(API_BASE_URL, path);
}

export function buildApiDebugState(path) {
  const resolvedUrl = buildApiUrl(path);
  return {
    configuredApiBaseUrl: CONFIGURED_API_BASE_URL || "",
    runtimeApiBaseUrl: API_BASE_URL || "",
    routeMode: API_ROUTE_MODE,
    resolvedUrl,
    resolvedUrlLabel: resolvedUrl || "same-origin",
  };
}

export function buildApiCandidateUrls(path) {
  const primary = buildApiUrl(path);
  if (typeof window === "undefined") return [primary];

  const sameOrigin = buildUrl("", path);
  const crossOriginConfigured = isCrossOriginApiTarget(API_BASE_URL);

  return dedupe([
    primary,
    crossOriginConfigured ? sameOrigin : "",
  ]);
}

export function buildAccessHeaders(accessCode = "") {
  const explicit = String(accessCode ?? "").trim();
  return explicit ? { "X-Neraium-Access-Code": explicit } : {};
}

function createAbortError() {
  if (typeof DOMException === "function") {
    return new DOMException("The API request was cancelled.", "AbortError");
  }
  const error = new Error("The API request was cancelled.");
  error.name = "AbortError";
  return error;
}

function responseMatchesExpectedType(response, expectedResponseType) {
  if (!expectedResponseType) return true;
  const contentType = response?.headers?.get?.("content-type") ?? "";
  if (!contentType) return true;
  if (expectedResponseType === "json") return /(?:application|text)\/(?:[a-z0-9.+-]*\+)?json\b/i.test(contentType);
  return contentType.toLowerCase().includes(String(expectedResponseType).toLowerCase());
}

function shouldTryNextCandidate({ response, expectedResponseType, method, hasNextCandidate }) {
  if (!hasNextCandidate || !["GET", "HEAD"].includes(method)) return false;
  if (response.status >= 500 || [404, 405, 408, 425].includes(response.status)) return true;
  return response.ok && !responseMatchesExpectedType(response, expectedResponseType);
}

function logFallback(path, method, reason, candidateIndex) {
  if (!import.meta.env.DEV) return;
  console.info("[neraium] API fallback candidate selected", {
    path: normalizeApiPath(path),
    method,
    reason,
    candidate: candidateIndex + 1,
  });
}

async function fetchCandidate(url, requestInit, timeoutMs, path, externalSignal = null) {
  const setTimer = typeof window !== "undefined" ? window.setTimeout.bind(window) : setTimeout;
  const clearTimer = typeof window !== "undefined" ? window.clearTimeout.bind(window) : clearTimeout;
  const controller = new AbortController();
  let timedOut = false;
  const handleExternalAbort = () => controller.abort(externalSignal?.reason);
  if (externalSignal?.aborted) throw createAbortError();
  externalSignal?.addEventListener("abort", handleExternalAbort, { once: true });
  const timeoutId = setTimer(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  try {
    return await fetch(url, { ...requestInit, signal: controller.signal });
  } catch (error) {
    if (externalSignal?.aborted) throw createAbortError();
    if (timedOut || error?.name === "AbortError") {
      const timeoutError = new Error(timeoutMessage(timeoutMs, path));
      timeoutError.name = "ApiTimeoutError";
      timeoutError.timeoutMs = timeoutMs;
      timeoutError.path = path;
      throw timeoutError;
    }
    throw error;
  } finally {
    clearTimer(timeoutId);
    externalSignal?.removeEventListener("abort", handleExternalAbort);
  }
}

export async function apiFetch(path, options = {}) {
  const { accessCode, expectedResponseType, headers, signal, timeoutMs, ...rest } = options;
  const normalizedMethod = String(rest.method || "GET").toUpperCase();
  const requestOptions = { ...rest };
  delete requestOptions.method;
  delete requestOptions.cache;
  const effectiveTimeoutMs = Number.isFinite(Number(timeoutMs)) && Number(timeoutMs) > 0
    ? Number(timeoutMs)
    : ["GET", "HEAD"].includes(normalizedMethod)
      ? API_TIMEOUT_MS
      : WRITE_API_TIMEOUT_MS;
  const normalizedPath = normalizeApiPath(path);
  const omitCustomAccessHeaders = ["GET", "HEAD"].includes(normalizedMethod) && isPublicReadonlyPath(normalizedPath);
  const accessHeaders = omitCustomAccessHeaders ? {} : buildAccessHeaders(accessCode);
  const candidates = buildApiCandidateUrls(path);
  let lastError = null;

  for (const [index, candidateUrl] of candidates.entries()) {
    const candidateIsCrossOrigin = typeof window !== "undefined"
      ? new URL(candidateUrl, window.location.origin).origin !== window.location.origin
      : false;
    const addNoCacheHeaders = (normalizedMethod === "GET" || normalizedMethod === "HEAD") && !candidateIsCrossOrigin;

    try {
      const response = await fetchCandidate(
        candidateUrl,
        {
          method: normalizedMethod,
          ...requestOptions,
          credentials: "include",
          cache: rest.cache ?? (normalizedMethod === "GET" || normalizedMethod === "HEAD" ? "no-store" : undefined),
          headers: {
            "X-Neraium-Workspace-Id": getCurrentWorkspaceId(),
            ...accessHeaders,
            ...(addNoCacheHeaders ? { "Cache-Control": "no-cache", Pragma: "no-cache" } : {}),
            ...(headers ?? {}),
          },
        },
        effectiveTimeoutMs,
        path,
        signal,
      );

      const hasNextCandidate = index < candidates.length - 1;
      if (shouldTryNextCandidate({ response, expectedResponseType, method: normalizedMethod, hasNextCandidate })) {
        const reason = response.ok ? "unexpected-content-type" : `http-${response.status}`;
        lastError = new Error(`API candidate returned ${response.status}`);
        logFallback(path, normalizedMethod, reason, index);
        continue;
      }

      if (typeof window !== "undefined" && response.status === 401 && !normalizedPath.startsWith("/api/auth/login") && !normalizedPath.startsWith("/api/auth/me")) {
        window.dispatchEvent(new CustomEvent("neraium:session-expired"));
      }
      return response;
    } catch (error) {
      lastError = error;
      if (signal?.aborted || error?.name === "AbortError") throw createAbortError();
      if (index < candidates.length - 1 && ["GET", "HEAD"].includes(normalizedMethod)) {
        logFallback(path, normalizedMethod, error?.name ?? "network-error", index);
        continue;
      }
      break;
    }
  }

  if (lastError?.name === "ApiTimeoutError") throw lastError;

  const networkError = new Error("The analysis service could not be reached. Check service health and retry.");
  networkError.name = "ApiNetworkError";
  networkError.path = path;
  networkError.cause = lastError;
  networkError.apiBaseUrl = API_BASE_URL || "same-origin";
  throw networkError;
}

export const API_CONFIG_WARNING = "";

export const APP_ACCESS_CONFIG_WARNING = "";

// Admission Gate is intentionally disabled until Exponent defines the final semantics.
export const ENABLE_ADMISSION_GATE = String(import.meta.env.VITE_ENABLE_ADMISSION_GATE ?? "0") === "1";
