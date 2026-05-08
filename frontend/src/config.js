const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
const configuredAppAccessCode = import.meta.env.VITE_APP_ACCESS_CODE?.trim();
const isProductionBuild = import.meta.env.PROD;

export const API_BASE_URL = configuredApiBaseUrl || (isProductionBuild ? "" : "http://127.0.0.1:8010");
export const APP_ACCESS_CODE = configuredAppAccessCode || (isProductionBuild ? "" : "neraium-dev");
export const HAS_APP_ACCESS_CODE = Boolean(APP_ACCESS_CODE);

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
