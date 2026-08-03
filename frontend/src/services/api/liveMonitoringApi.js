const COLLECTIONS = {
  configurations: {
    path: "/api/live-analysis/configurations",
    field: "configurations",
  },
  ingestionHealth: {
    path: "/api/telemetry/ingestion-health",
    field: "health",
  },
  analysisHealth: {
    path: "/api/live-analysis/health",
    field: "health",
  },
  runs: {
    path: "/api/live-analysis/runs?limit=100",
    field: "runs",
  },
  findings: {
    path: "/api/live-analysis/findings?limit=100",
    field: "findings",
  },
};

const inflightByClient = new WeakMap();

function requestError(response, path) {
  const status = Number(response?.status ?? 0) || null;
  const authorization = status === 401 || status === 403;
  const message = authorization
    ? "Your session cannot access Live Monitoring."
    : status && status >= 500
      ? "Live Monitoring is temporarily unavailable."
      : "Live Monitoring data could not be loaded.";
  return Object.assign(new Error(message), {
    name: "LiveMonitoringRequestError",
    kind: authorization ? "unauthorized" : "http",
    path,
    status,
  });
}

function normalizeRequestError(error, path) {
  if (error?.name === "AbortError") return error;
  if (error?.name === "LiveMonitoringRequestError") return error;
  const network = error?.name === "ApiNetworkError" || error?.name === "ApiTimeoutError" || error instanceof TypeError;
  return Object.assign(new Error(
    network
      ? "The Live Monitoring service could not be reached."
      : "Live Monitoring data could not be loaded.",
  ), {
    name: "LiveMonitoringRequestError",
    kind: network ? "network" : "request",
    path,
    status: null,
    cause: error,
  });
}

async function fetchCollection({ apiFetch, accessCode, signal, path, field }) {
  try {
    const response = await apiFetch(path, {
      accessCode,
      cache: "no-store",
      expectedResponseType: "json",
      signal,
    });
    if (!response?.ok) throw requestError(response, path);
    const payload = await response.json().catch(() => null);
    if (!payload || !Array.isArray(payload[field])) {
      throw Object.assign(new Error("Live Monitoring returned an incomplete response."), {
        name: "LiveMonitoringRequestError",
        kind: "malformed-response",
        path,
        status: Number(response.status) || null,
      });
    }
    return payload[field];
  } catch (error) {
    throw normalizeRequestError(error, path);
  }
}

export function fetchLiveAnalysisConfigurations(options) {
  return fetchCollection({ ...options, ...COLLECTIONS.configurations });
}

export function fetchTelemetryIngestionHealth(options) {
  return fetchCollection({ ...options, ...COLLECTIONS.ingestionHealth });
}

export function fetchLiveAnalysisHealth(options) {
  return fetchCollection({ ...options, ...COLLECTIONS.analysisHealth });
}

export function fetchLiveAnalysisRuns(options) {
  return fetchCollection({ ...options, ...COLLECTIONS.runs });
}

export function fetchLiveFindings(options) {
  return fetchCollection({ ...options, ...COLLECTIONS.findings });
}

function errorSummary(error) {
  return {
    kind: error?.kind ?? "request",
    message: String(error?.message ?? "Live Monitoring data could not be loaded."),
    path: error?.path ?? null,
    status: Number(error?.status ?? 0) || null,
  };
}

async function loadSnapshot({ apiFetch, accessCode }) {
  const requests = Object.entries(COLLECTIONS).map(async ([key, contract]) => {
    const value = await fetchCollection({ apiFetch, accessCode, ...contract });
    return [key, value];
  });
  const settled = await Promise.allSettled(requests);
  const snapshot = {
    configurations: [],
    ingestionHealth: [],
    analysisHealth: [],
    runs: [],
    findings: [],
    errors: {},
    status: "complete",
    refreshedAt: new Date().toISOString(),
  };

  settled.forEach((result, index) => {
    const key = Object.keys(COLLECTIONS)[index];
    if (result.status === "fulfilled") {
      snapshot[result.value[0]] = result.value[1];
    } else {
      snapshot.errors[key] = errorSummary(result.reason);
    }
  });

  const errors = Object.values(snapshot.errors);
  if (errors.length === settled.length && errors.every((error) => error.kind === "unauthorized")) {
    snapshot.status = "unauthorized";
  } else if (errors.length === settled.length) {
    snapshot.status = "error";
  } else if (errors.length) {
    snapshot.status = "partial";
  }
  return snapshot;
}

export function fetchLiveMonitoringSnapshot({ apiFetch, accessCode = "" } = {}) {
  if (typeof apiFetch !== "function") {
    return Promise.reject(new TypeError("apiFetch is required to load Live Monitoring."));
  }
  let clientInflight = inflightByClient.get(apiFetch);
  if (!clientInflight) {
    clientInflight = new Map();
    inflightByClient.set(apiFetch, clientInflight);
  }
  const key = String(accessCode ?? "");
  if (clientInflight.has(key)) return clientInflight.get(key);

  const request = loadSnapshot({ apiFetch, accessCode }).finally(() => {
    if (clientInflight.get(key) === request) clientInflight.delete(key);
  });
  clientInflight.set(key, request);
  return request;
}
