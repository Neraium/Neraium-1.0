import { apiFetch } from "../../config";

const LOCAL_AUTH_SESSION_KEY = "neraium.local_auth.session";

async function safeAuthFetch(path, options) {
  try {
    return await apiFetch(path, options);
  } catch {
    return null;
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

function isNotFoundResponse(response) {
  return Number(response?.status) === 404;
}

export async function loginUser({ email, password }) {
  const normalizedEmail = String(email ?? "").trim().toLowerCase();
  const response = await safeAuthFetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const payload = await readJson(response);
  if (!response || !response.ok) {
    throw new Error(detailMessage(payload, "Invalid email or password."));
  }
  setLocalSessionEmail(normalizedEmail);
  return payload;
}

export async function logoutUser() {
  const response = await safeAuthFetch("/api/auth/logout", { method: "POST" });
  if (!response || isNotFoundResponse(response)) {
    setLocalSessionEmail("");
    return { authenticated: false };
  }
  const payload = await readJson(response);
  if (!response.ok) throw new Error(detailMessage(payload, "Logout failed."));
  return payload;
}
