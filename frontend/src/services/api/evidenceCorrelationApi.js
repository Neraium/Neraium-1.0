export async function fetchRelatedEvidencePackages({ apiFetch, packageId, signal } = {}) {
  if (typeof apiFetch !== "function") throw new TypeError("apiFetch is required to load related findings.");
  const normalizedPackageId = String(packageId ?? "").trim();
  if (!normalizedPackageId) throw new TypeError("packageId is required to load related findings.");
  const path = `/api/data/evidence-packages/${encodeURIComponent(normalizedPackageId)}/related-packages`;
  const response = await apiFetch(path, { cache: "no-store", signal });
  let payload = null;
  try {
    payload = typeof response?.json === "function" ? await response.json() : null;
  } catch {
    payload = null;
  }
  if (!response?.ok) {
    const detail = typeof payload?.detail === "string" ? payload.detail : "Related findings could not be loaded.";
    throw Object.assign(new Error(detail), { status: response?.status ?? 0, payload });
  }
  return payload;
}
