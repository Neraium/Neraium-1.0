import { getCurrentWorkspaceId } from "../services/datasetSessionCache";

export const BASELINE_SELECTION_STORAGE_PREFIX = "neraium.baseline_selection";
const IDENTIFIER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

function identifier(value) {
  const normalized = String(value ?? "").trim();
  return IDENTIFIER_PATTERN.test(normalized) ? normalized : null;
}

export function baselineRoutePath(portfolioId, baselineId) {
  const portfolio = identifier(portfolioId);
  const baseline = identifier(baselineId);
  if (!portfolio || !baseline) return null;
  return `/portfolio/${encodeURIComponent(portfolio)}/baselines/${encodeURIComponent(baseline)}`;
}

export function parseBaselineRoute(pathname = typeof window === "undefined" ? "" : window.location.pathname) {
  const match = String(pathname || "").match(/^\/portfolio\/([^/]+)\/baselines\/([^/]+)\/?$/);
  if (!match) return null;
  try {
    const portfolioId = identifier(decodeURIComponent(match[1]));
    const baselineId = identifier(decodeURIComponent(match[2]));
    return portfolioId && baselineId ? { portfolioId, systemId: portfolioId, baselineId } : null;
  } catch {
    return null;
  }
}

export function baselineAnalysisRoutePath(portfolioId, baselineId, analysisRunId) {
  const baselinePath = baselineRoutePath(portfolioId, baselineId);
  const run = identifier(analysisRunId);
  return baselinePath && run ? `${baselinePath}/analyses/${encodeURIComponent(run)}` : null;
}

export function parseBaselineAnalysisRoute(pathname = typeof window === "undefined" ? "" : window.location.pathname) {
  const match = String(pathname || "").match(/^\/portfolio\/([^/]+)\/baselines\/([^/]+)\/analyses\/([^/]+)\/?$/);
  if (!match) return null;
  try {
    const portfolioId = identifier(decodeURIComponent(match[1]));
    const baselineId = identifier(decodeURIComponent(match[2]));
    const analysisRunId = identifier(decodeURIComponent(match[3]));
    return portfolioId && baselineId && analysisRunId
      ? { portfolioId, systemId: portfolioId, baselineId, analysisRunId }
      : null;
  } catch {
    return null;
  }
}

export function analysisBelongsToBaseline(result, identity) {
  const portfolioId = identifier(identity?.portfolioId);
  const systemId = identifier(identity?.systemId);
  const baselineId = identifier(identity?.baselineId);
  const expectedAnalysisRunId = identifier(identity?.analysisRunId);
  if (!result || !portfolioId || !baselineId) return false;
  const reference = result?.active_baseline_reference ?? {};
  const resultPortfolioId = identifier(result?.portfolio_id ?? result?.dataset_scope?.workspace_id);
  const resultSystemId = identifier(result?.system_id);
  const resultBaselineId = identifier(result?.baseline_id ?? reference?.model_id);
  const comparisonDatasetId = identifier(result?.comparison_dataset_id);
  const analysisRunId = identifier(result?.analysis_run_id ?? result?.run_id);
  const jobId = identifier(result?.job_id);
  const workflow = String(result?.workflow ?? "").trim();
  return workflow === "analyze_new_data"
    && resultPortfolioId === portfolioId
    && (!systemId || resultSystemId === systemId)
    && resultBaselineId === baselineId
    && identifier(reference?.model_id) === baselineId
    && Boolean(comparisonDatasetId)
    && Boolean(analysisRunId)
    && (!expectedAnalysisRunId || analysisRunId === expectedAnalysisRunId)
    && comparisonDatasetId === identifier(result?.dataset_id)
    && analysisRunId === jobId;
}

export function baselineIdentityFromResult(result, fallback = {}, stateSource = "completion_response") {
  const candidate = result?.candidate_model ?? result?.active_model ?? result ?? {};
  const source = candidate?.source ?? result?.source ?? {};
  const scope = result?.dataset_scope ?? candidate?.dataset_scope ?? {};
  const candidateId = identifier(
    result?.baseline_candidate_id
      ?? result?.candidate_id
      ?? candidate?.baseline_candidate_id
      ?? candidate?.model_id
      ?? fallback.candidateId,
  );
  const baselineId = identifier(
    result?.selected_baseline_id
      ?? result?.established_baseline_id
      ?? result?.baseline_id
      ?? candidate?.baseline_id
      ?? candidate?.model_id
      ?? fallback.baselineId
      ?? candidateId,
  );
  const portfolioId = identifier(
    result?.portfolio_id
      ?? result?.system_id
      ?? scope?.workspace_id
      ?? fallback.portfolioId
      ?? getCurrentWorkspaceId(),
  );
  if (!baselineId || !portfolioId) return null;
  return {
    jobId: identifier(result?.job_id ?? source?.job_id ?? fallback.jobId),
    uploadId: identifier(result?.upload_id ?? source?.upload_id ?? fallback.uploadId ?? result?.job_id ?? source?.job_id),
    datasetId: identifier(result?.dataset_id ?? source?.dataset_id ?? fallback.datasetId ?? result?.job_id ?? source?.job_id),
    candidateId: candidateId ?? baselineId,
    baselineId,
    portfolioId,
    systemId: identifier(result?.system_id ?? source?.system_id ?? fallback.systemId ?? portfolioId) ?? portfolioId,
    stateSource: ["completion_response", "hydration", "cache", "active_baseline_fetch"].includes(stateSource) ? stateSource : "hydration",
  };
}

function selectionStorageKey(portfolioId, baselineId) {
  return `${BASELINE_SELECTION_STORAGE_PREFIX}.${portfolioId}.${baselineId}`;
}

function currentSelectionStorageKey(portfolioId) {
  return `${BASELINE_SELECTION_STORAGE_PREFIX}.current.${portfolioId}`;
}

export function persistBaselineSelection(identity) {
  const normalized = baselineIdentityFromResult(identity, identity, identity?.stateSource ?? "completion_response");
  if (!normalized || typeof window === "undefined") return normalized;
  try {
    const serialized = JSON.stringify(normalized);
    window.localStorage.setItem(selectionStorageKey(normalized.portfolioId, normalized.baselineId), serialized);
    window.localStorage.setItem(currentSelectionStorageKey(normalized.portfolioId), serialized);
  } catch {
    // Route identity remains authoritative when optional browser storage is unavailable.
  }
  return normalized;
}

export function readPersistedBaselineSelection(portfolioId, baselineId = null) {
  const portfolio = identifier(portfolioId);
  const baseline = identifier(baselineId);
  if (!portfolio || typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(
      baseline ? selectionStorageKey(portfolio, baseline) : currentSelectionStorageKey(portfolio),
    );
    const parsed = raw ? JSON.parse(raw) : null;
    const normalized = baselineIdentityFromResult(parsed, parsed, "cache");
    return normalized && (!baseline || normalized.baselineId === baseline) ? normalized : null;
  } catch {
    return null;
  }
}

export function clearPersistedBaselineSelections() {
  if (typeof window === "undefined") return;
  try {
    for (let index = window.localStorage.length - 1; index >= 0; index -= 1) {
      const key = window.localStorage.key(index);
      if (key?.startsWith(`${BASELINE_SELECTION_STORAGE_PREFIX}.`)) window.localStorage.removeItem(key);
    }
  } catch {
    // Browser storage is an optional restoration aid.
  }
}
