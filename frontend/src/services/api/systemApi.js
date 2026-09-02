const FACILITY_SYSTEMS_DEDUPE_TTL_MS = 4000;
const facilitySystemsInflight = new Map();
const facilitySystemsCache = new Map();

export function clearFacilitySystemsCache() {
  facilitySystemsInflight.clear();
  facilitySystemsCache.clear();
}

export async function fetchFacilitySystems({ apiFetch, accessCode, scopeKey = "anonymous", portfolioId = "default", domainMode = null, includePersisted = false, forceRefresh = false }) {
  const key = `systems:${encodeURIComponent(scopeKey)}:${encodeURIComponent(portfolioId)}:${encodeURIComponent(String(domainMode ?? ""))}:${includePersisted ? 1 : 0}`;
  const now = Date.now();
  if (forceRefresh) {
    facilitySystemsCache.delete(key);
    const inFlight = facilitySystemsInflight.get(key);
    if (inFlight) return inFlight;
  } else {
    const cached = facilitySystemsCache.get(key);
    if (cached && cached.expiresAt > now) {
      return cached.value;
    }
    const inFlight = facilitySystemsInflight.get(key);
    if (inFlight) return inFlight;
  }

  const request = (async () => {
    const domainQuery = domainMode ? `&domain_mode=${encodeURIComponent(domainMode)}` : "";
    const response = await apiFetch(`/api/facility/systems?include_persisted=${includePersisted ? 1 : 0}${domainQuery}`, {
      accessCode,
      headers: { "X-Neraium-Workspace-Id": portfolioId },
    });
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw response;
      }
      throw new Error("Systems could not be loaded. Refresh and retry.");
    }
    const payload = await response.json();
    if (!Array.isArray(payload.systems)) {
      throw new Error("System data was incomplete. Refresh and retry.");
    }
    facilitySystemsCache.set(key, { expiresAt: Date.now() + FACILITY_SYSTEMS_DEDUPE_TTL_MS, value: payload });
    return payload;
  })();

  facilitySystemsInflight.set(key, request);
  try {
    return await request;
  } finally {
    facilitySystemsInflight.delete(key);
  }
}

export async function fetchEngineIdentity({ apiFetch, accessCode }) {
  return apiFetch("/api/intelligence/engine-identity", { accessCode });
}

export async function fetchDomainMode({ apiFetch, accessCode }) {
  const response = await apiFetch("/api/domain/mode", { accessCode });
  if (!response.ok) throw new Error("Telemetry context could not be loaded. Refresh and retry.");
  return response.json();
}
