const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/+$/, "");
const configuredFallbackApiBaseUrl = import.meta.env.VITE_API_FALLBACK_BASE_URL?.trim().replace(/\/+$/, "");
const isProductionBuild = import.meta.env.PROD;
const configuredApiTimeoutMs = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? "45000");
const API_TIMEOUT_MS = Number.isFinite(configuredApiTimeoutMs) && configuredApiTimeoutMs > 0
  ? configuredApiTimeoutMs
  : 45000;
const WRITE_API_TIMEOUT_MS = Math.max(API_TIMEOUT_MS, 300000);
const PRODUCTION_API_FALLBACK = "https://api.neraium.com";
const productionDefaultApiBaseUrl = configuredApiBaseUrl || (isProductionBuild ? PRODUCTION_API_FALLBACK : "http://127.0.0.1:8010");

export const API_BASE_URL = productionDefaultApiBaseUrl;

function appSiblingApiBaseUrl() {
  if (typeof window === "undefined" || !isProductionBuild) {
    return "";
  }

  const { protocol, hostname } = window.location;
  if (protocol !== "https:" || !hostname) {
    return "";
  }
  if (hostname === "app.neraium.com") {
    return PRODUCTION_API_FALLBACK;
  }
  if (hostname.endsWith(".neraium.com")) {
    return `https://api.${hostname.split(".").slice(-2).join(".")}`;
  }
  return "";
}

function isUnsafeMixedContentTarget(apiBaseUrl) {
  if (typeof window === "undefined" || !apiBaseUrl) {
    return false;
  }

  try {
    const current = new URL(window.location.href);
    const target = new URL(apiBaseUrl, window.location.origin);
    return current.protocol === "https:" && target.protocol === "http:";
  } catch {
    return false;
  }
}

function shouldIncludeSameOriginFallback(path, method = "GET") {
  const normalizedPath = normalizeApiPath(path);
  const normalizedMethod = String(method || "GET").toUpperCase();
  if (!isProductionBuild) {
    return true;
  }
  if (["GET", "HEAD"].includes(normalizedMethod)) {
    return true;
  }
  return !normalizedPath.startsWith("/api/");
}

function apiBaseCandidates(path = "/api/health", method = "GET", allowSameOriginFallback = null) {
  const siblingApi = appSiblingApiBaseUrl();
  const productionFallback = isProductionBuild ? PRODUCTION_API_FALLBACK : "";
  const configuredPrimary = API_BASE_URL;
  const configuredFallback = configuredFallbackApiBaseUrl;
  const includeSameOriginFallback = allowSameOriginFallback ?? shouldIncludeSameOriginFallback(path, method);

  // In production, never let mutating API requests fall through to the
  // static app origin. Upload/reset endpoints must target a real API host so
  // route mismatches surface once instead of generating same-origin 404 noise.
  const candidates = isProductionBuild
    ? [
      configuredPrimary || null,
      productionFallback || null,
      siblingApi || null,
      configuredFallback || null,
      includeSameOriginFallback ? "" : null,
    ]
    : [
      configuredPrimary,
      configuredFallback,
      siblingApi,
      productionFallback,
    ];

  const seen = new Set();
  return candidates.filter((value) => {
    if (value === null || value === undefined) return false;
    const normalized = (value ?? "").replace(/\/+$/, "");
    if (seen.has(normalized) || isUnsafeMixedContentTarget(normalized)) {
      return false;
    }
    seen.add(normalized);
    return true;
  });
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

export function buildApiCandidateUrls(path, options = {}) {
  const { method = "GET", allowSameOriginFallback = null } = options;
  return apiBaseCandidates(path, method, allowSameOriginFallback).map((apiBaseUrl) => buildUrl(apiBaseUrl, path));
}

function shouldRetryAgainstFallback(error) {
  return error instanceof TypeError || error?.name === "ApiNetworkError";
}

function shouldRetryOnHttpStatus({ status, apiBaseUrl, path }) {
  if (status >= 500 || status === 408 || status === 425 || status === 429) {
    return true;
  }
  if ([404, 405].includes(status) && isProductionBuild && !apiBaseUrl && String(path || "").startsWith("/api/")) {
    return true;
  }
  return false;
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
  const candidates = apiBaseCandidates(path, normalizedMethod);
  let lastError = null;

  for (const apiBaseUrl of candidates) {
    const controller = new AbortController();
    const timeoutId = setTimer(() => controller.abort(), effectiveTimeoutMs);
    const addNoCacheHeaders = (normalizedMethod === "GET" || normalizedMethod === "HEAD") && !isCrossOriginApiTarget(apiBaseUrl);
    const normalizedPath = normalizeApiPath(path);
    const omitCustomAccessHeaders = ["GET", "HEAD"].includes(normalizedMethod) && isPublicReadonlyPath(normalizedPath);
    const accessHeaders = omitCustomAccessHeaders ? {} : buildAccessHeaders(accessCode);

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
      const hasNextCandidate = apiBaseUrl !== candidates[candidates.length - 1];
      if (hasNextCandidate && shouldRetryOnHttpStatus({ status: response.status, apiBaseUrl, path })) {
        continue;
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
      networkError.apiBaseUrl = apiBaseUrl || "same-origin";
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
    ? "VITE_API_BASE_URL is not configured for this production build. Using HTTPS Neraium API fallback."
    : "VITE_API_BASE_URL is not configured. Using local development API.";

export const APP_ACCESS_CONFIG_WARNING = "";

// Admission Gate is intentionally disabled until Exponent defines the final semantics.
export const ENABLE_ADMISSION_GATE = String(import.meta.env.VITE_ENABLE_ADMISSION_GATE ?? "0") === "1";