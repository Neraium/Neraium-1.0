import { useCallback, useState } from 'react';

export default function useLatestUploadState({ hasAccess, apiAccessCode, apiFetch, uploadStateView }) {
  const [latestUploadResult, setLatestUploadResult] = useState(null);
  const [latestUploadSnapshot, setLatestUploadSnapshot] = useState(uploadStateView.buildEmptyLatestUploadSnapshot());

  const loadLatestUploadState = useCallback(async () => {
    if (!hasAccess) {
      return false;
    }

    try {
      const response = await apiFetch('/api/data/latest-upload', { accessCode: apiAccessCode });
      if (!response.ok) {
        throw new Error(Unexpected response: );
      }

      const payload = await response.json();
      setLatestUploadSnapshot(payload ?? uploadStateView.buildEmptyLatestUploadSnapshot());
      const latestResult = payload?.latest_result;
      if (uploadStateView.hasFullUploadResult(latestResult)) {
        setLatestUploadResult(latestResult);
        return true;
      }
      setLatestUploadResult(null);
      return false;
    } catch {
      setLatestUploadSnapshot(uploadStateView.buildEmptyLatestUploadSnapshot());
      setLatestUploadResult(null);
      return false;
    }
  }, [apiAccessCode, apiFetch, hasAccess, uploadStateView]);

  return { latestUploadResult, setLatestUploadResult, latestUploadSnapshot, setLatestUploadSnapshot, loadLatestUploadState };
}
