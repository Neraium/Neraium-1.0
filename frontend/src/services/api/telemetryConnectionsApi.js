const JSON_HEADERS = Object.freeze({ "Content-Type": "application/json" });

function encodeId(value) {
  return encodeURIComponent(String(value ?? "").trim());
}

async function safePayload(response) {
  try {
    const payload = await response.json();
    return payload && typeof payload === "object" ? payload : {};
  } catch {
    return {};
  }
}

function safeError(payload, response) {
  const detail = payload?.detail && typeof payload.detail === "object" ? payload.detail : payload;
  const detailMessage = typeof payload?.detail === "string" ? payload.detail : null;
  const status = Number(response?.status ?? 0) || null;
  const fallback = status === 401 || status === 403
    ? "Your current role cannot perform this telemetry action."
    : status === 404
      ? "This connection is not available in the current facility."
      : status === 409
        ? "The connection changed or already has an active operation. Refresh and retry."
        : "The telemetry service could not complete this action. Retry safely.";
  return Object.assign(new Error(String(detail?.message || detailMessage || fallback)), {
    name: "TelemetryConnectionRequestError",
    code: String(detail?.code || `telemetry_http_${status || "error"}`),
    status,
    retryable: detail?.retryable === true || status === 408 || status === 429 || status >= 500,
    requestId: detail?.request_id ? String(detail.request_id) : null,
  });
}

async function request(apiFetch, accessCode, path, options = {}) {
  const response = await apiFetch(path, {
    accessCode,
    expectedResponseType: "json",
    ...options,
    headers: {
      ...(options.body !== undefined ? JSON_HEADERS : {}),
      ...(options.headers ?? {}),
    },
  });
  const payload = await safePayload(response);
  if (!response?.ok) throw safeError(payload, response);
  return payload;
}

function body(value) {
  return JSON.stringify(value ?? {});
}

export function listTelemetryConnections({ apiFetch, accessCode, signal }) {
  return request(apiFetch, accessCode, "/api/data-connections", { signal, cache: "no-store" });
}

export function listTelemetryProviders({ apiFetch, accessCode, signal }) {
  return request(apiFetch, accessCode, "/api/data-connections/providers", { signal, cache: "no-store" });
}

export function listCanonicalSignalConcepts({ apiFetch, accessCode, signal }) {
  return request(apiFetch, accessCode, "/api/data-connections/signal-concepts", { signal, cache: "no-store" });
}

export function getFacilityContext({ apiFetch, accessCode, signal }) {
  return request(apiFetch, accessCode, "/api/facility/context", { signal, cache: "no-store" });
}

export function putFacilityContext({ apiFetch, accessCode, context, signal }) {
  return request(apiFetch, accessCode, "/api/facility/context", {
    method: "PUT",
    signal,
    body: body(context),
  });
}

export function getTelemetryConnection({ apiFetch, accessCode, connectionId, signal }) {
  return request(apiFetch, accessCode, `/api/data-connections/${encodeId(connectionId)}`, { signal, cache: "no-store" });
}

export function createTelemetryConnection({ apiFetch, accessCode, connection, signal }) {
  return request(apiFetch, accessCode, "/api/data-connections", {
    method: "POST",
    signal,
    body: body(connection),
  });
}

export function putTelemetryCredentials({ apiFetch, accessCode, connectionId, values, signal }) {
  return request(apiFetch, accessCode, `/api/data-connections/${encodeId(connectionId)}/credentials`, {
    method: "PUT",
    signal,
    body: body({ values }),
  });
}

export function validateTelemetryConnection({ apiFetch, accessCode, connectionId, signal }) {
  return request(apiFetch, accessCode, `/api/data-connections/${encodeId(connectionId)}/validate`, {
    method: "POST",
    signal,
  });
}

export function discoverTelemetrySignals({ apiFetch, accessCode, connectionId, checkpoint = null, signal }) {
  return request(apiFetch, accessCode, `/api/data-connections/${encodeId(connectionId)}/discover`, {
    method: "POST",
    signal,
    body: body(checkpoint ? { checkpoint } : {}),
  });
}

export function listTelemetrySignals({ apiFetch, accessCode, connectionId, mappingStatus = "", limit = 250, offset = 0, signal }) {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (mappingStatus) query.set("mapping_status", mappingStatus);
  return request(apiFetch, accessCode, `/api/data-connections/${encodeId(connectionId)}/signals?${query}`, { signal, cache: "no-store" });
}

export function mapTelemetrySignal({ apiFetch, accessCode, connectionId, signalId, mapping, signal }) {
  return request(apiFetch, accessCode, `/api/data-connections/${encodeId(connectionId)}/signals/${encodeId(signalId)}/mapping`, {
    method: "PUT",
    signal,
    body: body(mapping),
  });
}

export function setTelemetryConnectionEnabled({ apiFetch, accessCode, connectionId, enabled, signal }) {
  return request(apiFetch, accessCode, `/api/data-connections/${encodeId(connectionId)}/${enabled ? "enable" : "disable"}`, {
    method: "POST",
    signal,
  });
}

export function listTelemetryRuns({ apiFetch, accessCode, connectionId, limit = 50, offset = 0, signal }) {
  return request(apiFetch, accessCode, `/api/data-connections/${encodeId(connectionId)}/runs?limit=${limit}&offset=${offset}`, { signal, cache: "no-store" });
}

export function listTelemetryErrors({ apiFetch, accessCode, connectionId, limit = 50, offset = 0, signal }) {
  return request(apiFetch, accessCode, `/api/data-connections/${encodeId(connectionId)}/errors?limit=${limit}&offset=${offset}`, { signal, cache: "no-store" });
}

export function retryTelemetryRun({ apiFetch, accessCode, connectionId, runId, signal }) {
  return request(apiFetch, accessCode, `/api/data-connections/${encodeId(connectionId)}/runs/${encodeId(runId)}/retry`, {
    method: "POST",
    signal,
  });
}

export function startTelemetryBackfill({ apiFetch, accessCode, connectionId, startAt, endAt, signal }) {
  return request(apiFetch, accessCode, `/api/data-connections/${encodeId(connectionId)}/backfills`, {
    method: "POST",
    signal,
    body: body({ start_at: startAt, end_at: endAt }),
  });
}
