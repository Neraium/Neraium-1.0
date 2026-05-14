export async function fetchFacilitySystems({ apiFetch, accessCode }) {
  const response = await apiFetch("/api/facility/systems", { accessCode });
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
