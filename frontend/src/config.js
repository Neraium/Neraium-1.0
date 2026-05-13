const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/+$/, "");
const isProductionBuild = import.meta.env.PROD;
const configuredApiTimeoutMs = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? "45000");
const API_TIMEOUT_MS = Number.isFinite(configuredApiTimeoutMs) && configuredApiTimeoutMs > 0
  ? configuredApiTimeoutMs
  : 45000;
const WRITE_API_TIMEOUT_MS = Math.max(API_TIMEOUT_MS, 120000);

export const API_BASE_URL = configuredApiBaseUrl || (isProductionBuild ? "" : "http://127.0.0.1:8010");

function isCrossOriginApiTarget() {
  if (typeof window === "undefined" || !API_BASE_URL) {
    return false;
  }

  try {
    const target = new URL(API_BASE_URL, window.location.origin);
    return target.origin !== window.location.origin;
  } catch {
    return false;
  }
}

function timeoutMessage(timeoutMs, path) {
  return `API request timed out after ${timeoutMs}ms while calling ${path}.`;
}

export function buildAccessHeaders() {
  return {};
}

export function apiFetch(path, options = {}) {
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
  const controller = new AbortController();
  const setTimer = typeof window !== "undefined" ? window.setTimeout.bind(window) : setTimeout;
  const clearTimer = typeof window !== "undefined" ? window.clearTimeout.bind(window) : clearTimeout;
  const timeoutId = setTimer(() => controller.abort(), effectiveTimeoutMs);
  const addNoCacheHeaders = (normalizedMethod === "GET" || normalizedMethod === "HEAD") && !isCrossOriginApiTarget();
  return fetch(`${API_BASE_URL}${path}`, {
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
  })
    .catch((error) => {
      if (error?.name === "AbortError") {
        const timeoutError = new Error(timeoutMessage(effectiveTimeoutMs, path));
        timeoutError.name = "ApiTimeoutError";
        timeoutError.timeoutMs = effectiveTimeoutMs;
        timeoutError.path = path;
        throw timeoutError;
      }
      throw error;
    })
    .finally(() => {
      clearTimer(timeoutId);
    });
}

export const API_CONFIG_WARNING = configuredApiBaseUrl
  ? ""
  : isProductionBuild
    ? "VITE_API_BASE_URL is not configured for this production build."
    : "VITE_API_BASE_URL is not configured. Using local development API.";

export const APP_ACCESS_CONFIG_WARNING = "";
