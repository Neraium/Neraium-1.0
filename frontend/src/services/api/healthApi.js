export async function fetchApiHealth({ apiFetch, accessCode }) {
  const response = await apiFetch("/api/health", { accessCode });
  if (!response.ok) {
    throw new Error(`Unexpected response: ${response.status}`);
  }
  const payload = await response.json();
  if (payload.status !== "ok") {
    throw new Error("Health response was not ok.");
  }
  return payload;
}
