import { readJsonPayload, buildUploadRequestError } from "../../viewModels/uploadFlow";

const baselineResultCache = new Map();
const baselineResultInflight = new Map();
const BASELINE_CACHE_TTL_MS = 30_000;

export function baselineQueryKey(portfolioId, baselineId) {
  return `baseline:${String(portfolioId ?? "").trim()}:${String(baselineId ?? "").trim()}`;
}

export function clearBaselineResultCache({ portfolioId = null, baselineId = null } = {}) {
  const exactKey = portfolioId && baselineId ? baselineQueryKey(portfolioId, baselineId) : null;
  for (const [key, entry] of baselineResultInflight.entries()) {
    if (exactKey ? key === exactKey : !portfolioId || key.startsWith(`baseline:${portfolioId}:`)) {
      entry.controller.abort();
      baselineResultInflight.delete(key);
    }
  }
  for (const key of baselineResultCache.keys()) {
    if (exactKey ? key === exactKey : !portfolioId || key.startsWith(`baseline:${portfolioId}:`)) {
      baselineResultCache.delete(key);
    }
  }
}

export async function fetchBaselineResultById({
  apiFetch,
  accessCode,
  portfolioId,
  baselineId,
  forceRefresh = false,
  signal = null,
} = {}) {
  const key = baselineQueryKey(portfolioId, baselineId);
  if (!portfolioId || !baselineId) throw new Error("An exact portfolio and baseline identifier are required.");
  if (forceRefresh) clearBaselineResultCache({ portfolioId, baselineId });
  const cached = baselineResultCache.get(key);
  if (!forceRefresh && cached?.expiresAt > Date.now()) return { result: cached.value, source: "cache" };
  if (!forceRefresh && baselineResultInflight.has(key)) return baselineResultInflight.get(key).promise;

  const controller = new AbortController();
  const abort = () => controller.abort(signal?.reason);
  if (signal?.aborted) abort();
  signal?.addEventListener("abort", abort, { once: true });
  const path = `/api/data/baselines/${encodeURIComponent(baselineId)}`;
  const promise = (async () => {
    try {
      const response = await apiFetch(path, {
        accessCode,
        signal: controller.signal,
        headers: { "X-Neraium-Workspace-Id": portfolioId },
      });
      const payload = await readJsonPayload(response, { route: path, phase: "baseline_result" });
      if (!response.ok || !payload?.candidate_model) throw buildUploadRequestError(response, payload, "baseline_result");
      const returnedId = String(payload?.established_baseline_id ?? payload?.candidate_model?.model_id ?? "").trim();
      if (returnedId !== String(baselineId)) throw new Error("The baseline response did not match the requested baseline identifier.");
      baselineResultCache.set(key, { value: payload, expiresAt: Date.now() + BASELINE_CACHE_TTL_MS });
      return { result: payload, source: "hydration" };
    } finally {
      signal?.removeEventListener("abort", abort);
      if (baselineResultInflight.get(key)?.controller === controller) baselineResultInflight.delete(key);
    }
  })();
  baselineResultInflight.set(key, { controller, promise });
  return promise;
}
