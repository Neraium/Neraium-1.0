import { apiFetch } from "../../config";

const LOCAL_AUTH_SESSION_KEY = "neraium.local_auth.session";
const SIGN_IN_SERVICE_UNAVAILABLE = "The sign-in service is temporarily unavailable. Try again.";
const SESSION_SERVICE_UNAVAILABLE = "The session service is temporarily unavailable. Refresh and retry.";
export const SESSION_INITIALIZATION_TIMEOUT_MS = 8000;
const SESSION_CANDIDATE_TIMEOUT_MS = 4000;
const AUTH_WRITE_TIMEOUT_MS = 15000;

export const SESSION_INITIALIZATION_ERROR_KIND = Object.freeze({
  BACKEND_UNAVAILABLE: "backend-unavailable",
  MALFORMED_RESPONSE: "malformed-response",
  TIMEOUT: "timeout",
});

export class SessionInitializationError extends Error {
  constructor(kind, message, cause = null) {
    super(message);
    this.name = "SessionInitializationError";
    this.kind = kind;
    if (cause) this.cause = cause;
  }
}

function createAbortError() {
  if (typeof DOMException === "function") {
    return new DOMException("Session verification was cancelled.", "AbortError");
  }
  const error = new Error("Session verification was cancelled.");
  error.name = "AbortError";
  return error;
}

function createSessionError(kind, message, cause = null) {
  return new SessionInitializationError(kind, message, cause);
}

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

async function readSessionJson(response) {
  try {
    return await response.json();
  } catch (error) {
    throw createSessionError(
      SESSION_INITIALIZATION_ERROR_KIND.MALFORMED_RESPONSE,
      "The session service returned an unexpected response. Retry session verification.",
      error,
    );
  }
}

function detailMessage(payload, fallback) {
  if (typeof payload?.detail === "string" && payload.detail.trim()) return payload.detail;
  if (typeof payload?.message === "string" && payload.message.trim()) return payload.message;
  return fallback;
}

function logStorageWarning(operation, error) {
  if (!import.meta.env.DEV) return;
  console.warn("[neraium] local session marker unavailable", {
    operation,
    name: error?.name ?? "StorageError",
  });
}

function setLocalSessionEmail(email) {
  if (typeof window === "undefined") return;
  try {
    if (!email) {
      window.localStorage.removeItem(LOCAL_AUTH_SESSION_KEY);
      return;
    }
    window.localStorage.setItem(LOCAL_AUTH_SESSION_KEY, String(email).trim().toLowerCase());
  } catch (error) {
    logStorageWarning(email ? "write" : "remove", error);
  }
}

async function fetchSessionResponse({ signal, timeoutMs }) {
  if (signal?.aborted) throw createAbortError();

  const controller = new AbortController();
  let timeoutId = null;
  let removeAbortListener = () => {};

  const timeoutPromise = new Promise((_, reject) => {
    timeoutId = setTimeout(() => {
      controller.abort();
      reject(createSessionError(
        SESSION_INITIALIZATION_ERROR_KIND.TIMEOUT,
        "Session verification timed out. Check your connection and retry.",
      ));
    }, timeoutMs);
  });

  const callerAbortPromise = new Promise((_, reject) => {
    if (!signal) return;
    const handleAbort = () => {
      controller.abort(signal.reason);
      reject(createAbortError());
    };
    signal.addEventListener("abort", handleAbort, { once: true });
    removeAbortListener = () => signal.removeEventListener("abort", handleAbort);
  });

  const requestPromise = apiFetch(
    "/api/auth/me",
    {
      cache: "no-store",
      expectedResponseType: "json",
      signal: controller.signal,
      timeoutMs: Math.min(timeoutMs, SESSION_CANDIDATE_TIMEOUT_MS),
    },
  );

  try {
    return await Promise.race([requestPromise, timeoutPromise, callerAbortPromise]);
  } finally {
    clearTimeout(timeoutId);
    removeAbortListener();
  }
}

function normalizeSessionPayload(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload) || typeof payload.authenticated !== "boolean") {
    throw createSessionError(
      SESSION_INITIALIZATION_ERROR_KIND.MALFORMED_RESPONSE,
      "The session service returned an unexpected response. Retry session verification.",
    );
  }
  if (payload.authenticated) {
    if (!payload.user || typeof payload.user !== "object" || Array.isArray(payload.user)) {
      throw createSessionError(
        SESSION_INITIALIZATION_ERROR_KIND.MALFORMED_RESPONSE,
        "The session service returned an incomplete authenticated session. Retry session verification.",
      );
    }
    return payload;
  }
  return { ...payload, authenticated: false, user: null, session: payload.session ?? null };
}

export async function fetchCurrentUser({ signal, timeoutMs = SESSION_INITIALIZATION_TIMEOUT_MS } = {}) {
  const boundedTimeoutMs = Number.isFinite(Number(timeoutMs)) && Number(timeoutMs) > 0
    ? Number(timeoutMs)
    : SESSION_INITIALIZATION_TIMEOUT_MS;

  let response;
  try {
    response = await fetchSessionResponse({ signal, timeoutMs: boundedTimeoutMs });
  } catch (error) {
    if (signal?.aborted || error?.name === "AbortError") throw createAbortError();
    if (error instanceof SessionInitializationError) throw error;
    if (error?.name === "ApiTimeoutError") {
      throw createSessionError(
        SESSION_INITIALIZATION_ERROR_KIND.TIMEOUT,
        "Session verification timed out. Check your connection and retry.",
        error,
      );
    }
    throw createSessionError(
      SESSION_INITIALIZATION_ERROR_KIND.BACKEND_UNAVAILABLE,
      SESSION_SERVICE_UNAVAILABLE,
      error,
    );
  }

  if (response.status === 401) {
    return { authenticated: false, user: null, session: null };
  }
  if (!response.ok) {
    throw createSessionError(
      SESSION_INITIALIZATION_ERROR_KIND.BACKEND_UNAVAILABLE,
      SESSION_SERVICE_UNAVAILABLE,
    );
  }

  return normalizeSessionPayload(await readSessionJson(response));
}

export async function loginUser({ email, password }) {
  const normalizedEmail = String(email ?? "").trim().toLowerCase();
  const response = await authFetch(
    "/api/auth/login",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: normalizedEmail, password }),
      timeoutMs: AUTH_WRITE_TIMEOUT_MS,
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

export async function registerEmployee({ firstName, lastName, email, password, passwordConfirmation, inviteToken }) {
  const normalizedEmail = String(email ?? "").trim().toLowerCase();
  const response = await authFetch(
    "/api/auth/register",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        first_name: String(firstName ?? "").trim(),
        last_name: String(lastName ?? "").trim(),
        email: normalizedEmail,
        password,
        password_confirmation: passwordConfirmation,
        invite_token: inviteToken,
      }),
      timeoutMs: AUTH_WRITE_TIMEOUT_MS,
    },
    "Employee registration is temporarily unavailable. Try again.",
  );
  const payload = await readJson(response);
  if (!response.ok) {
    if (response.status >= 500) throw new Error("Employee registration is temporarily unavailable. Try again.");
    if (response.status === 429) throw new Error(detailMessage(payload, "Too many registration attempts. Wait and try again."));
    if (response.status === 409) throw new Error(detailMessage(payload, "An account already exists for this email."));
    throw new Error(detailMessage(payload, "Review your details and try again."));
  }
  setLocalSessionEmail(normalizedEmail);
  return payload;
}

export async function logoutUser() {
  const response = await authFetch(
    "/api/auth/logout",
    { method: "POST", timeoutMs: AUTH_WRITE_TIMEOUT_MS },
    "The sign-out service is unavailable. Check the connection and try again.",
  );
  const payload = await readJson(response);
  if (!response.ok) throw new Error(detailMessage(payload, "Sign out failed. Try again."));
  setLocalSessionEmail("");
  return payload;
}
