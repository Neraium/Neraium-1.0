const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/+$/, "");
const configuredFallbackApiBaseUrl = import.meta.env.VITE_API_FALLBACK_BASE_URL?.trim().replace(/\/+$/, "");
const isProductionBuild = import.meta.env.PROD;
const configuredApiTimeoutMs = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? "45000");
const API_TIMEOUT_MS = Number.isFinite(configuredApiTimeoutMs) && configuredApiTimeoutMs > 0
  ? configuredApiTimeoutMs
  : 45000;
const WRITE_API_TIMEOUT_MS = Math.max(API_TIMEOUT_MS, 120000);
const PRODUCTION_API_FALLBACK = "https://api.neraium.com";
const productionDefaultApiBaseUrl = configuredApiBaseUrl || (isProductionBuild ? PRODUCTION_API_FALLBACK : "http://127.0.0.1:8010");

export const API_BASE_URL = productionDefaultApiBaseUrl;

function apiBaseCandidates() {
  const candidates = [
    API_BASE_URL,
    configuredFallbackApiBaseUrl,
    isProductionBuild && !configuredApiBaseUrl ? PRODUCTION_API_FALLBACK : "",
  ];

  return candidates.filter((value, index, list) => value !== null && value !== undefined && list.indexOf(value) === index);
}

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

function buildUrl(apiBaseUrl, path) {
  return `${apiBaseUrl}${path}`;
}

function shouldRetryAgainstFallback(error) {
  return error instanceof TypeError || error?.name === "ApiNetworkError";
}

export function buildAccessHeaders() {
  return {};
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
  const candidates = apiBaseCandidates();
  let lastError = null;

  for (const apiBaseUrl of candidates) {
    const controller = new AbortController();
    const timeoutId = setTimer(() => controller.abort(), effectiveTimeoutMs);
    const addNoCacheHeaders = (normalizedMethod === "GET" || normalizedMethod === "HEAD") && !isCrossOriginApiTarget(apiBaseUrl);

    try {
      return await fetch(buildUrl(apiBaseUrl, path), {
        method: normalizedMethod,
        ...requestOptions,
        credentials: "include",
        cache: rest.cache ?? (normalizedMethod === "GET" || normalizedMethod === "HEAD" ? "no-store" : undefined),
        headers: {
          ...buildAccessHeaders(),
          ...(addNoCacheHeaders
            ? { "Cache-Control": "no-cache", Pragma: "no-cache" }
            : {}),
          ...(headers ?? {}),
        },
        signal: controller.signal,
      });
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
      lastError = networkError;

      if (!shouldRetryAgainstFallback(networkError) || apiBaseUrl === candidates[candidates.length - 1]) {
        throw networkError;
      }
    } finally {
      clearTimer(timeoutId);
    }
  }

  throw lastError ?? new Error(`API request failed while calling ${path}.`);
}

export const API_CONFIG_WARNING = configuredApiBaseUrl
  ? ""
  : isProductionBuild
    ? "VITE_API_BASE_URL is not configured for this production build. Using production API endpoint directly."
    : "VITE_API_BASE_URL is not configured. Using local development API.";

export const APP_ACCESS_CONFIG_WARNING = "";
