export async function fetchCanonicalCognitionState({ apiFetch, accessCode, mode = "live" }) {
  const response = await apiFetch(
    `/api/facility/cognition-state?mode=${encodeURIComponent(mode)}`,
    { accessCode },
  );
  if (!response.ok) {
    throw new Error(`Unexpected response: ${response.status}`);
  }
  return response.json();
}

