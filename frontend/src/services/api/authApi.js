import { apiFetch } from "../../config";

const LOCAL_AUTH_USERS_KEY = "neraium.local_auth.users";
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

function loadLocalUsers() {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(LOCAL_AUTH_USERS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveLocalUsers(users) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LOCAL_AUTH_USERS_KEY, JSON.stringify(users));
}

function readLocalSessionEmail() {
  if (typeof window === "undefined") return "";
  return String(window.localStorage.getItem(LOCAL_AUTH_SESSION_KEY) ?? "");
}

function setLocalSessionEmail(email) {
  if (typeof window === "undefined") return;
  if (!email) {
    window.localStorage.removeItem(LOCAL_AUTH_SESSION_KEY);
    return;
  }
  window.localStorage.setItem(LOCAL_AUTH_SESSION_KEY, String(email).trim().toLowerCase());
}

function resolveLocalUserByEmail(email) {
  const normalized = String(email ?? "").trim().toLowerCase();
  return loadLocalUsers().find((user) => String(user?.email ?? "").toLowerCase() === normalized) ?? null;
}

function isNotFoundResponse(response) {
  return Number(response?.status) === 404;
}

export async function fetchCurrentUser() {
  const response = await safeAuthFetch("/api/auth/me");
  if (!response || !response.ok || isNotFoundResponse(response)) {
    const email = readLocalSessionEmail();
    const user = email ? resolveLocalUserByEmail(email) : null;
    return { authenticated: Boolean(user), user };
  }
  const payload = await readJson(response);
  return payload;
}

export async function signupUser({ name, email, password }) {
  const normalizedEmail = String(email ?? "").trim().toLowerCase();
  const response = await safeAuthFetch("/api/auth/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password }),
  });
  if (!response || !response.ok) {
    const payload = await readJson(response);
    const detail = detailMessage(payload, "");
    const canFallbackLocal =
      !response
      || isNotFoundResponse(response)
      || response.status >= 500
      || detail.toLowerCase().includes("not found")
      || detail.toLowerCase().includes("unavailable");
    if (!canFallbackLocal) {
      throw new Error(detailMessage(payload, "Sign up failed."));
    }
    if (!normalizedEmail || !normalizedEmail.includes("@")) throw new Error("Enter a valid email address.");
    if (String(password ?? "").length < 8) throw new Error("Password must be at least 8 characters.");
    const users = loadLocalUsers();
    if (users.some((user) => String(user?.email ?? "").toLowerCase() === normalizedEmail)) {
      throw new Error("An account with this email already exists.");
    }
    const user = {
      email: normalizedEmail,
      name: String(name ?? "").trim() || normalizedEmail.split("@", 1)[0],
      created_at: new Date().toISOString(),
      password,
    };
    users.push(user);
    saveLocalUsers(users);
    setLocalSessionEmail(normalizedEmail);
    return { authenticated: true, user: { email: user.email, name: user.name, created_at: user.created_at } };
  }
  const payload = await readJson(response);
  return payload;
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
    // Resilient fallback: when server auth is unavailable or state was reset,
    // still allow local-login accounts created in this browser.
    const localUser = resolveLocalUserByEmail(normalizedEmail);
    if (localUser && String(localUser?.password ?? "") === String(password ?? "")) {
      setLocalSessionEmail(normalizedEmail);
      return {
        authenticated: true,
        user: { email: localUser.email, name: localUser.name, created_at: localUser.created_at },
      };
    }
    throw new Error(detailMessage(payload, "Invalid email or password. If this is your first login here, create account again."));
  }
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
