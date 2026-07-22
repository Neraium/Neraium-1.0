import { apiFetch } from "../../config";

const LOCAL_AUTH_SESSION_KEY = "neraium.local_auth.session";
const SIGN_IN_SERVICE_UNAVAILABLE = "The sign-in service is temporarily unavailable. Try again.";
const SESSION_SERVICE_UNAVAILABLE = "The session service is temporarily unavailable. Refresh and retry.";

async function authFetch(path, options, unavailableMessage) {
  try {
    const response = await apiFetch(path, options);
    if (!response) throw new Error(unavailableMessage);
    return response;
  } catch {
    throw new Error(unavailableMessage);
  }
}

async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function detailMessage(payload, fallback) {
  if (typeof payload?.detail === "string" && payload.detail.trim()) return payload.detail;
  if (typeof payload?.message === "string" && payload.message.trim()) return payload.message;
  return fallback;
}

function setLocalSessionEmail(email) {
  if (typeof window === "undefined") return;
  if (!email) {
    window.localStorage.removeItem(LOCAL_AUTH_SESSION_KEY);
    return;
  }
  window.localStorage.setItem(LOCAL_AUTH_SESSION_KEY, String(email).trim().toLowerCase());
}

export async function fetchCurrentUser() {
  const response = await authFetch(
    "/api/auth/me",
    { cache: "no-store" },
    SESSION_SERVICE_UNAVAILABLE,
  );
  const payload = await readJson(response);
  if (!response.ok) {
    if (response.status >= 500) throw new Error(SESSION_SERVICE_UNAVAILABLE);
    throw new Error(detailMessage(payload, "Unable to verify your session."));
  }
  return payload;
}

export async function loginUser({ email, password }) {
  const normalizedEmail = String(email ?? "").trim().toLowerCase();
  const response = await authFetch(
    "/api/auth/login",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: normalizedEmail, password }),
    },
    SIGN_IN_SERVICE_UNAVAILABLE,
  );
  const payload = await readJson(response);
  if (!response.ok) {
    if (response.status >= 500) throw new Error(SIGN_IN_SERVICE_UNAVAILABLE);
    if (response.status === 429) {
      throw new Error(detailMessage(payload, "Too many sign-in attempts. Wait and try again."));
    }
    if (response.status === 401) {
      throw new Error(detailMessage(payload, "Invalid email or password."));
    }
    throw new Error(detailMessage(payload, "Sign in failed. Check your details and try again."));
  }
  setLocalSessionEmail(normalizedEmail);
  return payload;
}

export async function logoutUser() {
  const response = await authFetch(
    "/api/auth/logout",
    { method: "POST" },
    "The sign-out service is unavailable. Check the connection and try again.",
  );
  const payload = await readJson(response);
  if (!response.ok) throw new Error(detailMessage(payload, "Sign out failed. Try again."));
  setLocalSessionEmail("");
  return payload;
}
