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
export const API_ROUTE_MODE = isProductionBuild ? "same-origin" : (configuredApiBaseUrl ? "configured-host" : "local-backend");

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
  return `API request timed out after ${timeoutMs}ms while calling ${path}.`;
}

function isPublicReadonlyPath(path) {
  const normalized = String(path || "").toLowerCase();
  return (
    normalized.startsWith("/api/data/latest-upload")
    || normalized.startsWith("/api/data/upload-status/")
    || normalized.startsWith("/api/facility/systems")
    || normalized.startsWith("/api/health")
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
  return [buildApiUrl(path)];
}

export function buildAccessHeaders(accessCode = "") {
  const explicit = String(accessCode ?? "").trim();
  return explicit ? { "X-Neraium-Access-Code": explicit } : {};
}

export async function apiFetch(path, options = {}) {
  const { accessCode, headers, timeoutMs, ...rest } = options;
  const normalizedMethod = String(rest.method || "GET").toUpperCase();
  const requestOptions = { ...rest };
  delete requestOptions.method;
  delete requestOptions.cache;
  const effectiveTimeoutMs = Number.isFinite(Number(timeoutMs)) && Number(timeoutMs) > 0
    ? Number(timeoutMs)
    : ["GET", "HEAD"].includes(normalizedMethod)
      ? API_TIMEOUT_MS
      : WRITE_API_TIMEOUT_MS;
  const setTimer = typeof window !== "undefined" ? window.setTimeout.bind(window) : setTimeout;
  const clearTimer = typeof window !== "undefined" ? window.clearTimeout.bind(window) : clearTimeout;
  const controller = new AbortController();
  const timeoutId = setTimer(() => controller.abort(), effectiveTimeoutMs);
  const addNoCacheHeaders = (normalizedMethod === "GET" || normalizedMethod === "HEAD") && !isCrossOriginApiTarget(API_BASE_URL);
  const normalizedPath = normalizeApiPath(path);
  const omitCustomAccessHeaders = ["GET", "HEAD"].includes(normalizedMethod) && isPublicReadonlyPath(normalizedPath);
  const accessHeaders = omitCustomAccessHeaders ? {} : buildAccessHeaders(accessCode);

  const apiBaseUrl = API_BASE_URL;
  try {
    const response = await fetch(buildUrl(apiBaseUrl, path), {
      method: normalizedMethod,
      ...requestOptions,
      credentials: "include",
      cache: rest.cache ?? (normalizedMethod === "GET" || normalizedMethod === "HEAD" ? "no-store" : undefined),
      headers: {
        ...accessHeaders,
        ...(addNoCacheHeaders
          ? { "Cache-Control": "no-cache", Pragma: "no-cache" }
          : {}),
        ...(headers ?? {}),
      },
      signal: controller.signal,
    });
    if (typeof window !== "undefined" && response.status === 401 && !normalizedPath.startsWith("/api/auth/login") && !normalizedPath.startsWith("/api/auth/me")) {
      window.dispatchEvent(new CustomEvent("neraium:session-expired"));
    }
    return response;
  } catch (error) {
    if (error?.name === "AbortError") {
      const timeoutError = new Error(timeoutMessage(effectiveTimeoutMs, path));
      timeoutError.name = "ApiTimeoutError";
      timeoutError.timeoutMs = effectiveTimeoutMs;
      timeoutError.path = path;
      throw timeoutError;
    }

    const networkError = new Error(`API network unavailable while calling ${path}.`);
    networkError.name = "ApiNetworkError";
    networkError.path = path;
    networkError.cause = error;
    networkError.apiBaseUrl = API_BASE_URL || "same-origin";
    throw networkError;
  } finally {
    clearTimer(timeoutId);
  }
}

export const API_CONFIG_WARNING = configuredApiBaseUrl
  ? ""
  : isProductionBuild
    ? ""
    : "VITE_API_BASE_URL is not configured. Using local development API.";

export const APP_ACCESS_CONFIG_WARNING = "";

// Admission Gate is intentionally disabled until Exponent defines the final semantics.
export const ENABLE_ADMISSION_GATE = String(import.meta.env.VITE_ENABLE_ADMISSION_GATE ?? "0") === "1";
