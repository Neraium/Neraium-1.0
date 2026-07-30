const IDENTIFIER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const COMPLETED_STATUSES = new Set(["complete", "completed", "success", "save_complete"]);

function identifier(value) {
  const normalized = String(value ?? "").trim();
  return IDENTIFIER_PATTERN.test(normalized) ? normalized : null;
}

function text(value) {
  const normalized = String(value ?? "").trim();
  return normalized || null;
}

function recordsFrom(payload) {
  if (!payload || typeof payload !== "object") return [];
  return [
    payload?.data?.result,
    payload?.result?.data,
    payload?.data,
    payload?.result,
    payload?.payload,
    payload,
  ].filter((value, index, values) => value && typeof value === "object" && values.indexOf(value) === index);
}

function recordScore(value) {
  const candidate = value?.candidate_model;
  return [
    value?.baselineId,
    value?.baseline_id,
    value?.established_baseline_id,
    value?.selected_baseline_id,
    value?.baseline_model_id,
    candidate?.baseline_id,
  ].filter(Boolean).length + (candidate ? 2 : 0);
}

function first(records, reader) {
  for (const record of records) {
    const value = reader(record);
    if (value !== null && value !== undefined && String(value).trim()) return value;
  }
  return null;
}

export class BaselineCreationContractError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = "BaselineCreationContractError";
    this.errorType = "baseline_creation_contract_invalid";
    this.retryable = true;
    Object.assign(this, details);
  }
}

/**
 * @typedef {Object} BaselineCreationResponse
 * @property {string} status
 * @property {string|null} datasetId
 * @property {string|null} jobId
 * @property {string|null} baselineId
 * @property {string|null} workspacePath
 * @property {string|null} createdAt
 * @property {string|null} portfolioId
 * @property {string|null} systemId
 */

/** Normalize all legacy/nested server shapes once, at the API boundary. */
export function normalizeBaselineCreationResponse(payload, fallback = {}, { requireBaselineId = false } = {}) {
  const records = recordsFrom(payload);
  const ranked = [...records].sort((left, right) => recordScore(right) - recordScore(left));
  const record = ranked[0] ?? {};
  const ordered = [record, ...records.filter((value) => value !== record), fallback].filter(Boolean);
  const candidate = ordered.find((value) => value?.candidate_model)?.candidate_model ?? {};
  const source = candidate?.source ?? ordered.find((value) => value?.source)?.source ?? {};
  const scope = ordered.find((value) => value?.dataset_scope)?.dataset_scope ?? {};

  // modelId/candidateId are deliberately excluded: neither is a baseline ID.
  const baselineId = identifier(first(ordered, (value) => (
    value?.baselineId
      ?? value?.baseline_id
      ?? value?.established_baseline_id
      ?? value?.selected_baseline_id
      ?? value?.baseline_model_id
      ?? value?.candidate_model?.baseline_id
  )));
  const jobId = identifier(first(ordered, (value) => value?.jobId ?? value?.job_id ?? value?.candidate_model?.source?.job_id) ?? source?.job_id);
  const datasetId = identifier(first(ordered, (value) => value?.datasetId ?? value?.dataset_id ?? value?.candidate_model?.source?.dataset_id) ?? source?.dataset_id);
  const portfolioId = identifier(first(ordered, (value) => (
    value?.portfolioId ?? value?.portfolio_id ?? value?.candidate_model?.source?.portfolio_id ?? value?.dataset_scope?.workspace_id
  )) ?? source?.portfolio_id ?? scope?.workspace_id);
  const systemId = identifier(first(ordered, (value) => (
    value?.systemId ?? value?.system_id ?? value?.candidate_model?.source?.system_id
  )) ?? source?.system_id ?? portfolioId);
  const candidateId = identifier(first(ordered, (value) => value?.candidateId ?? value?.baseline_candidate_id ?? value?.candidate_model?.baseline_candidate_id));
  const rawStatus = text(first(ordered, (value) => value?.status ?? value?.job_state ?? value?.processing_state)) ?? "unknown";
  const normalizedStatus = rawStatus.toLowerCase().replaceAll("-", "_");
  const completed = COMPLETED_STATUSES.has(normalizedStatus) || normalizedStatus === "completed_compatibility";
  const workspacePath = text(first(ordered, (value) => value?.workspacePath ?? value?.workspace_path))
    ?? (portfolioId && baselineId ? `/portfolio/${encodeURIComponent(portfolioId)}/baselines/${encodeURIComponent(baselineId)}` : null);
  const createdAt = text(first(ordered, (value) => value?.createdAt ?? value?.created_at ?? value?.completed_at ?? value?.candidate_model?.created_at));

  if (requireBaselineId && !baselineId) {
    throw new BaselineCreationContractError("A completed baseline response did not include baselineId.", {
      jobId,
      datasetId,
      status: normalizedStatus,
    });
  }

  return {
    ...record,
    status: completed ? "completed" : normalizedStatus,
    datasetId,
    jobId,
    baselineId,
    workspacePath,
    createdAt,
    portfolioId,
    systemId: systemId ?? portfolioId,
    candidateId,
  };
}
