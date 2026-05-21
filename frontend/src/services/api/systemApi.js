export async function fetchFacilitySystems({ apiFetch, accessCode, domainMode = null }) {
  const domainQuery = domainMode ? `&domain_mode=${encodeURIComponent(domainMode)}` : "";
  const response = await apiFetch(`/api/facility/systems?include_persisted=0${domainQuery}`, { accessCode });
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
  return payload;
}

export async function fetchEngineIdentity({ apiFetch, accessCode }) {
  return apiFetch("/api/intelligence/engine-identity", { accessCode });
}

export async function fetchDomainMode({ apiFetch, accessCode }) {
  const response = await apiFetch("/api/domain/mode", { accessCode });
  if (!response.ok) throw new Error(`Unexpected response: ${response.status}`);
  return response.json();
}
