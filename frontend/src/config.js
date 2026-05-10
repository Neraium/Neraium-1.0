const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/+$/, "");
const isProductionBuild = import.meta.env.PROD;

export const API_BASE_URL = configuredApiBaseUrl || (isProductionBuild ? "" : "http://127.0.0.1:8010");

export function buildAccessHeaders() {
  return {};
}

export function apiFetch(path, options = {}) {
  const { accessCode, headers, ...rest } = options;
  return fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    credentials: "include",
    headers: {
      ...buildAccessHeaders(),
      ...(headers ?? {}),
    },
  });
}

export const API_CONFIG_WARNING = configuredApiBaseUrl
  ? ""
  : isProductionBuild
    ? "VITE_API_BASE_URL is not configured for this production build."
    : "VITE_API_BASE_URL is not configured. Using local development API.";

export const APP_ACCESS_CONFIG_WARNING = "";


