export async function fetchApiHealth({ apiFetch, accessCode }) {
  const readyRequest = apiFetch("/api/ready", { accessCode })
    .then(async (readyResponse) => (readyResponse.ok ? readyResponse.json() : null))
    .catch(() => null);
  const response = await apiFetch("/api/health", { accessCode });
  if (!response.ok) {
    throw new Error("Platform health could not be checked. Refresh and retry.");
  }
  const payload = await response.json();
  if (payload.status !== "ok") {
    throw new Error("The platform is reporting a service problem. Retry in a few minutes.");
  }
  return { ...payload, ready: await readyRequest };
}
