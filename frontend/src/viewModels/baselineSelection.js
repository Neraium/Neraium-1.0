import { getCurrentWorkspaceId } from "../services/datasetSessionCache";
import { normalizeBaselineCreationResponse } from "../contracts/baselineCreation";

export const BASELINE_SELECTION_STORAGE_PREFIX = "neraium.baseline_selection";
const IDENTIFIER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

function identifier(value) {
  const normalized = String(value ?? "").trim();
  return IDENTIFIER_PATTERN.test(normalized) ? normalized : null;
}

function currentPortfolioIdentity(baselineId) {
  const portfolioId = identifier(getCurrentWorkspaceId());
  const persisted = portfolioId ? readPersistedBaselineSelection(portfolioId, baselineId) : null;
  return portfolioId ? {
    ...persisted,
    portfolioId,
    systemId: identifier(persisted?.systemId) ?? portfolioId,
    baselineId,
  } : null;
}

export function baselineRoutePath(_portfolioId, baselineId) {
  const baseline = identifier(baselineId);
  return baseline ? `/baselines/${encodeURIComponent(baseline)}/ready` : null;
}

export function baselineComparisonRoutePath(_portfolioId, baselineId) {
  const baseline = identifier(baselineId);
  return baseline ? `/baselines/${encodeURIComponent(baseline)}/comparisons/new` : null;
}

export function parseBaselineRoute(pathname = typeof window === "undefined" ? "" : window.location.pathname) {
  const canonical = String(pathname || "").match(/^\/baselines\/([^/]+)\/ready\/?$/);
  if (canonical) {
    try {
      const baselineId = identifier(decodeURIComponent(canonical[1]));
      return baselineId ? currentPortfolioIdentity(baselineId) : null;
    } catch {
      return null;
    }
  }

  // Preserve existing bookmarked baseline-detail URLs while all new handoffs use
  // the explicit baseline-ready lifecycle route.
  const legacy = String(pathname || "").match(/^\/portfolio\/([^/]+)\/baselines\/([^/]+)\/?$/);
  if (!legacy) return null;
  try {
    const portfolioId = identifier(decodeURIComponent(legacy[1]));
    const baselineId = identifier(decodeURIComponent(legacy[2]));
    const persisted = portfolioId && baselineId ? readPersistedBaselineSelection(portfolioId, baselineId) : null;
    return portfolioId && baselineId ? { ...persisted, portfolioId, systemId: identifier(persisted?.systemId) ?? portfolioId, baselineId } : null;
  } catch {
    return null;
  }
}

export function parseBaselineComparisonRoute(pathname = typeof window === "undefined" ? "" : window.location.pathname) {
  const match = String(pathname || "").match(/^\/baselines\/([^/]+)\/comparisons\/new\/?$/);
  if (!match) return null;
  try {
    const baselineId = identifier(decodeURIComponent(match[1]));
    return baselineId ? currentPortfolioIdentity(baselineId) : null;
  } catch {
    return null;
  }
}

export function baselineAnalysisRoutePath(_portfolioId, _baselineId, analysisRunId) {
  const run = identifier(analysisRunId);
  return run ? `/analyses/${encodeURIComponent(run)}` : null;
}

export function parseBaselineAnalysisRoute(pathname = typeof window === "undefined" ? "" : window.location.pathname) {
  const canonical = String(pathname || "").match(/^\/analyses\/([^/]+)\/?$/);
  if (canonical) {
    try {
      const analysisRunId = identifier(decodeURIComponent(canonical[1]));
      return analysisRunId ? { analysisRunId } : null;
    } catch {
      return null;
    }
  }

  const legacy = String(pathname || "").match(/^\/portfolio\/([^/]+)\/baselines\/([^/]+)\/analyses\/([^/]+)\/?$/);
  if (!legacy) return null;
  try {
    const portfolioId = identifier(decodeURIComponent(legacy[1]));
    const baselineId = identifier(decodeURIComponent(legacy[2]));
    const analysisRunId = identifier(decodeURIComponent(legacy[3]));
    return portfolioId && baselineId && analysisRunId
      ? { portfolioId, systemId: portfolioId, baselineId, analysisRunId }
      : null;
  } catch {
    return null;
  }
}

export function analysisBelongsToBaseline(result, identity = {}) {
  if (!result) return false;
  const portfolioId = identifier(identity?.portfolioId);
  const systemId = identifier(identity?.systemId);
  const baselineId = identifier(identity?.baselineId);
  const expectedAnalysisRunId = identifier(identity?.analysisRunId);
  const reference = result?.active_baseline_reference ?? {};
  const resultPortfolioId = identifier(result?.portfolio_id ?? result?.dataset_scope?.workspace_id);
  const resultSystemId = identifier(result?.system_id);
  const resultBaselineId = identifier(result?.baseline_id ?? reference?.model_id);
  const baselineDatasetId = identifier(result?.baseline_dataset_id ?? reference?.dataset_id);
  const comparisonDatasetId = identifier(result?.comparison_dataset_id);
  const analysisRunId = identifier(result?.comparison_analysis_id ?? result?.analysis_run_id ?? result?.run_id);
  const jobId = identifier(result?.job_id);
  const workflow = String(result?.workflow ?? "").trim();
  const status = String(result?.status ?? "").trim().toUpperCase();
  const processingState = String(result?.processing_state ?? "").trim().toLowerCase();
  return workflow === "analyze_new_data"
    && status === "COMPLETE"
    && processingState === "complete"
    && result?.sii_completed === true
    && Boolean(resultPortfolioId)
    && Boolean(resultSystemId)
    && Boolean(resultBaselineId)
    && Boolean(baselineDatasetId)
    && Boolean(comparisonDatasetId)
    && baselineDatasetId !== comparisonDatasetId
    && Boolean(analysisRunId)
    && (!portfolioId || resultPortfolioId === portfolioId)
    && (!systemId || resultSystemId === systemId)
    && (!baselineId || resultBaselineId === baselineId)
    && identifier(reference?.model_id) === resultBaselineId
    && identifier(reference?.dataset_id) === baselineDatasetId
    && (!expectedAnalysisRunId || analysisRunId === expectedAnalysisRunId)
    && comparisonDatasetId === identifier(result?.dataset_id)
    && analysisRunId === jobId;
}

export function baselineIdentityFromResult(result, fallback = {}, stateSource = "completion_response") {
  const normalized = normalizeBaselineCreationResponse(result, {
    ...fallback,
    portfolioId: fallback.portfolioId ?? getCurrentWorkspaceId(),
  });
  const baselineId = identifier(normalized.baselineId);
  const portfolioId = identifier(normalized.portfolioId ?? fallback.portfolioId ?? getCurrentWorkspaceId());
  if (!baselineId || !portfolioId) return null;
  return {
    jobId: identifier(normalized.jobId ?? fallback.jobId),
    uploadId: identifier(
      result?.uploadId
        ?? result?.upload_id
        ?? normalized?.candidate_model?.source?.upload_id
        ?? fallback.uploadId
        ?? normalized.jobId,
    ),
    datasetId: identifier(normalized.datasetId ?? fallback.datasetId),
    candidateId: identifier(normalized.candidateId ?? fallback.candidateId),
    baselineId,
    portfolioId,
    systemId: identifier(normalized.systemId ?? fallback.systemId ?? portfolioId) ?? portfolioId,
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
