export async function fetchReplayTimeline({ apiFetch, accessCode, intervals = 24, replayCompression = 1, mode = "live" }) {
  const response = await apiFetch(
    `/api/replay/timeline?intervals=${encodeURIComponent(intervals)}&replay_compression=${encodeURIComponent(replayCompression)}&mode=${encodeURIComponent(mode)}`,
    { accessCode },
  );
  if (!response.ok) {
    throw new Error(`Unexpected response: ${response.status}`);
  }
  return response.json();
}

export async function fetchReplayFrame({ apiFetch, accessCode, timestamp, intervals = 24, mode = "live" }) {
  const response = await apiFetch(
    `/api/replay/frame/${encodeURIComponent(timestamp)}?intervals=${encodeURIComponent(intervals)}&mode=${encodeURIComponent(mode)}`,
    { accessCode },
  );
  if (!response.ok) {
    throw new Error(`Unexpected response: ${response.status}`);
  }
  return response.json();
}

export async function fetchReplayRange({
  apiFetch,
  accessCode,
  startTimestamp,
  endTimestamp,
  intervals = 24,
  mode = "live",
}) {
  const response = await apiFetch(
    `/api/replay/range?start_timestamp=${encodeURIComponent(startTimestamp)}&end_timestamp=${encodeURIComponent(endTimestamp)}&intervals=${encodeURIComponent(intervals)}&mode=${encodeURIComponent(mode)}`,
    { accessCode },
  );
  if (!response.ok) {
    throw new Error(`Unexpected response: ${response.status}`);
  }
  return response.json();
}
