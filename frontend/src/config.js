const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/+$/, "");
const isProductionBuild = import.meta.env.PROD;
const configuredApiTimeoutMs = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? "15000");
const API_TIMEOUT_MS = Number.isFinite(configuredApiTimeoutMs) && configuredApiTimeoutMs > 0
  ? configuredApiTimeoutMs
  : 15000;

export const API_BASE_URL = configuredApiBaseUrl || (isProductionBuild ? "" : "http://127.0.0.1:8010");

export function buildAccessHeaders() {
  return {};
}

export function apiFetch(path, options = {}) {
  const { accessCode, headers, method, cache, ...rest } = options;
  const normalizedMethod = String(method || "GET").toUpperCase();
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  return fetch(`${API_BASE_URL}${path}`, {
    method: normalizedMethod,
    ...rest,
    credentials: "include",
    cache: cache ?? (normalizedMethod === "GET" || normalizedMethod === "HEAD" ? "no-store" : undefined),
    headers: {
      ...buildAccessHeaders(),
      ...(normalizedMethod === "GET" || normalizedMethod === "HEAD"
        ? { "Cache-Control": "no-cache", Pragma: "no-cache" }
        : {}),
      ...(headers ?? {}),
    },
    signal: controller.signal,
  })
    .catch((error) => {
      if (error?.name === "AbortError") {
        throw new Error(`API request timed out after ${API_TIMEOUT_MS}ms.`);
      }
      throw error;
    })
    .finally(() => {
      window.clearTimeout(timeoutId);
    });
}

export const API_CONFIG_WARNING = configuredApiBaseUrl
  ? ""
  : isProductionBuild
    ? "VITE_API_BASE_URL is not configured for this production build."
    : "VITE_API_BASE_URL is not configured. Using local development API.";

export const APP_ACCESS_CONFIG_WARNING = "";
