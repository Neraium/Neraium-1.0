import { readJsonPayload, buildUploadRequestError } from "../../viewModels/uploadFlow";

const baselineResultCache = new Map();
const baselineResultInflight = new Map();
const BASELINE_CACHE_TTL_MS = 30_000;
export const BASELINE_DETAIL_TIMEOUT_MS = 15_000;

function normalizedKeyPart(value, fallback = "unknown") {
  return encodeURIComponent(String(value ?? "").trim() || fallback);
}

export function baselineQueryKey(scopeKey, portfolioId, baselineId) {
  return [
    "baseline",
    normalizedKeyPart(scopeKey, "anonymous"),
    normalizedKeyPart(portfolioId),
    normalizedKeyPart(baselineId),
  ].join(":");
}

export function clearBaselineResultCache({ scopeKey = null, portfolioId = null, baselineId = null } = {}) {
  const prefix = [
    "baseline",
    scopeKey ? normalizedKeyPart(scopeKey) : null,
    portfolioId ? normalizedKeyPart(portfolioId) : null,
    baselineId ? normalizedKeyPart(baselineId) : null,
  ];
  const matches = (key) => {
    const parts = String(key).split(":");
    return (!prefix[1] || parts[1] === prefix[1])
      && (!prefix[2] || parts[2] === prefix[2])
      && (!prefix[3] || parts[3] === prefix[3]);
  };
  for (const [key, entry] of baselineResultInflight.entries()) {
    if (matches(key)) {
      entry.controller.abort();
      baselineResultInflight.delete(key);
    }
  }
  for (const key of baselineResultCache.keys()) {
    if (matches(key)) baselineResultCache.delete(key);
  }
}

let baselineRequestSequence = 0;

function requestIdentifier() {
  baselineRequestSequence += 1;
  const suffix = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${baselineRequestSequence}`;
  return `baseline-detail-${suffix}`;
}

function baselineRequestError(error, { path, requestId, elapsedMs }) {
  if (error?.name === "AbortError") return error;
  const timeout = error?.name === "ApiTimeoutError";
  const network = error?.name === "ApiNetworkError" || error instanceof TypeError;
  const status = Number(error?.status ?? error?.payload?.response_status ?? 0) || (timeout ? 408 : null);
  const errorType = timeout
    ? "timeout"
    : network
      ? "network"
      : error?.errorType ?? error?.payload?.error_type ?? (status ? `http_${status}` : "baseline_request_failed");
  const safeMessage = timeout
    ? "The baseline service did not respond within 15 seconds. Retry the request."
    : network
      ? "The baseline service could not be reached. Check the connection and retry."
      : status === 404
        ? "The requested baseline was not found in this portfolio."
        : status === 401 || status === 403
          ? "Your session cannot access this baseline. Sign in again or contact an administrator."
          : status >= 500
            ? "The baseline service is temporarily unavailable. Retry the request."
            : "The baseline could not be loaded safely. Retry the request.";
  return Object.assign(new Error(safeMessage), {
    name: "BaselineRequestError",
    status,
    errorType,
    requestId: error?.requestId ?? error?.payload?.request_id ?? requestId,
    path,
    elapsedMs,
    retryable: timeout || network || status === 408 || status === 429 || status >= 500,
    cause: error,
  });
}

function validateBaselinePayload(payload, { portfolioId, baselineId }) {
  const candidate = payload?.candidate_model ?? {};
  const source = candidate?.source ?? {};
  const returnedId = String(payload?.baseline_id ?? payload?.established_baseline_id ?? candidate?.baseline_id ?? candidate?.model_id ?? "").trim();
  const returnedPortfolioId = String(payload?.portfolio_id ?? source?.portfolio_id ?? "").trim();
  const returnedSystemId = String(payload?.system_id ?? source?.system_id ?? "").trim();
  if (returnedId !== String(baselineId)) throw new Error("The baseline response did not match the requested baseline identifier.");
  if (returnedPortfolioId !== String(portfolioId) || String(source?.portfolio_id ?? "").trim() !== String(portfolioId)) {
    throw new Error("The baseline response did not match the requested portfolio identifier.");
  }
  if (!returnedSystemId || String(source?.system_id ?? "").trim() !== returnedSystemId) {
    throw new Error("The baseline response did not contain a valid system identity.");
  }
}

export async function fetchBaselineResultById({
  apiFetch,
  accessCode,
  scopeKey = "anonymous",
  portfolioId,
  baselineId,
  forceRefresh = false,
  signal = null,
  timeoutMs = BASELINE_DETAIL_TIMEOUT_MS,
} = {}) {
  const key = baselineQueryKey(scopeKey, portfolioId, baselineId);
  if (!portfolioId || !baselineId) throw new Error("An exact portfolio and baseline identifier are required.");
  if (forceRefresh) clearBaselineResultCache({ scopeKey, portfolioId, baselineId });
  const cached = baselineResultCache.get(key);
  if (!forceRefresh && cached?.expiresAt > Date.now()) {
    return { result: cached.value, source: "cache", diagnostics: { ...cached.diagnostics, source: "cache" } };
  }
  if (!forceRefresh && baselineResultInflight.has(key)) return baselineResultInflight.get(key).promise;

  const controller = new AbortController();
  const abort = () => controller.abort(signal?.reason);
  if (signal?.aborted) abort();
  signal?.addEventListener("abort", abort, { once: true });
  const path = `/api/data/portfolios/${encodeURIComponent(portfolioId)}/baselines/${encodeURIComponent(baselineId)}`;
  const requestId = requestIdentifier();
  const startedAt = Date.now();
  const promise = (async () => {
    try {
      const response = await apiFetch(path, {
        accessCode,
        signal: controller.signal,
        timeoutMs,
        expectedResponseType: "json",
        headers: {
          "X-Neraium-Workspace-Id": portfolioId,
          "X-Request-Id": requestId,
        },
      });
      const payload = await readJsonPayload(response, { route: path, phase: "baseline_result" });
      if (!response.ok || !payload?.candidate_model) throw buildUploadRequestError(response, payload, "baseline_result");
      validateBaselinePayload(payload, { portfolioId, baselineId });
      const diagnostics = {
        path,
        requestId: payload?.request_id ?? response?.headers?.get?.("x-request-id") ?? requestId,
        status: Number(response.status),
        elapsedMs: Date.now() - startedAt,
        cacheKey: key,
        source: "hydration",
      };
      baselineResultCache.set(key, { value: payload, diagnostics, expiresAt: Date.now() + BASELINE_CACHE_TTL_MS });
      return { result: payload, source: "hydration", diagnostics };
    } catch (error) {
      if (controller.signal.aborted && signal?.aborted) throw error;
      throw baselineRequestError(error, { path, requestId, elapsedMs: Date.now() - startedAt });
    } finally {
      signal?.removeEventListener("abort", abort);
      if (baselineResultInflight.get(key)?.controller === controller) baselineResultInflight.delete(key);
    }
  })();
  baselineResultInflight.set(key, { controller, promise });
  return promise;
}
