const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/+$/, "");
const configuredAppAccessCode = import.meta.env.VITE_APP_ACCESS_CODE?.trim();
const isProductionBuild = import.meta.env.PROD;

export const API_BASE_URL = configuredApiBaseUrl || (isProductionBuild ? "" : "http://127.0.0.1:8010");
export const APP_ACCESS_CODE = configuredAppAccessCode || (isProductionBuild ? "" : "neraium-dev");
export const HAS_APP_ACCESS_CODE = Boolean(APP_ACCESS_CODE);
export const ACCESS_CODE_HEADER = "X-Neraium-Access-Code";
export const ACCESS_CODE_SESSION_KEY = "neraium_access_code";

export function resolveAccessCode(accessCode = APP_ACCESS_CODE) {
  if (accessCode) {
    return accessCode;
  }
  if (typeof window === "undefined") {
    return "";
  }
  return window.sessionStorage.getItem(ACCESS_CODE_SESSION_KEY) || "";
}

export function buildAccessHeaders(accessCode = APP_ACCESS_CODE) {
  const resolvedAccessCode = resolveAccessCode(accessCode);
  console.log("ACCESS CODE:", resolvedAccessCode); return resolvedAccessCode ? { [ACCESS_CODE_HEADER]: resolvedAccessCode } : {};
}

export function apiFetch(path, options = {}) {
  const { accessCode, headers, ...rest } = options;
  return fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    credentials: "include",
    headers: {
      ...buildAccessHeaders(accessCode || APP_ACCESS_CODE),
      ...(headers ?? {}),
    },
  });
}

export const API_CONFIG_WARNING = configuredApiBaseUrl
  ? ""
  : isProductionBuild
    ? "VITE_API_BASE_URL is not configured for this production build."
    : "VITE_API_BASE_URL is not configured. Using local development API.";

export const APP_ACCESS_CONFIG_WARNING = configuredAppAccessCode
  ? ""
  : isProductionBuild
    ? "Access is not configured for this production build."
    : "Local development access is enabled.";


