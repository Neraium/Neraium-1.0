const FACILITY_SYSTEMS_DEDUPE_TTL_MS = 4000;
const facilitySystemsInflight = new Map();
const facilitySystemsCache = new Map();

export async function fetchFacilitySystems({ apiFetch, accessCode, domainMode = null }) {
  const key = `systems:${String(domainMode ?? "")}`;
  const now = Date.now();
  const cached = facilitySystemsCache.get(key);
  if (cached && cached.expiresAt > now) {
    return cached.value;
  }
  const inFlight = facilitySystemsInflight.get(key);
  if (inFlight) return inFlight;

  const request = (async () => {
  const domainQuery = domainMode ? `&domain_mode=${encodeURIComponent(domainMode)}` : "";
  const response = await apiFetch(`/api/facility/systems?include_persisted=1${domainQuery}`, { accessCode });
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      throw response;
    }
    throw new Error(`Unexpected response: ${response.status}`);
  }
  const payload = await response.json();
  if (!Array.isArray(payload.systems)) {
    throw new Error("Facility systems payload was incomplete.");
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
  if (!response.ok) throw new Error(`Unexpected response: ${response.status}`);
  return response.json();
}
