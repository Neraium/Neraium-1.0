import { apiFetch } from "../../config";

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

export async function fetchCurrentUser() {
  const response = await apiFetch("/api/auth/me");
  const payload = await readJson(response);
  if (!response.ok) throw new Error(detailMessage(payload, "Failed to load session."));
  return payload;
}

export async function signupUser({ name, email, password }) {
  const response = await apiFetch("/api/auth/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password }),
  });
  const payload = await readJson(response);
  if (!response.ok) throw new Error(detailMessage(payload, "Sign up failed."));
  return payload;
}

export async function loginUser({ email, password }) {
  const response = await apiFetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const payload = await readJson(response);
  if (!response.ok) throw new Error(detailMessage(payload, "Login failed."));
  return payload;
}

export async function logoutUser() {
  const response = await apiFetch("/api/auth/logout", { method: "POST" });
  const payload = await readJson(response);
  if (!response.ok) throw new Error(detailMessage(payload, "Logout failed."));
  return payload;
}

