import { useCallback, useRef, useState } from 'react';

export default function useBackendHealth({ hasAccess, apiAccessCode, apiFetch, apiBaseUrl, formatClockTime, formatEndpoint, setBackendError }) {
  const [apiStatus, setApiStatus] = useState({
    state: 'checking',
    label: 'Sync pending',
    detail: 'Establishing facility sync.',
    checkedAt: null,
    attemptCount: 0,
    endpoint: formatEndpoint(apiBaseUrl),
    message: '',
  });
  const healthCheckAttemptsRef = useRef(0);

  const checkApiHealth = useCallback(async (trigger = 'scheduled') => {
    if (!hasAccess) {
      return false;
    }

    const checkTime = new Date();
    const attemptCount = healthCheckAttemptsRef.current + 1;
    healthCheckAttemptsRef.current = attemptCount;

    try {
      const response = await apiFetch('/api/health', { accessCode: apiAccessCode });
      if (!response.ok) {
        throw new Error(Unexpected response: );
      }

      const payload = await response.json();
      if (payload.status !== 'ok') {
        throw new Error('Health response was not ok.');
      }

      setApiStatus({
        state: 'online',
        label: 'API Connected',
        detail: Last sync  CT.,
        checkedAt: checkTime.toISOString(),
        attemptCount,
        endpoint: formatEndpoint(apiBaseUrl),
        message: trigger === 'scheduled' ? 'Backend sync current.' : 'Facility sync refreshed.',
      });
      return true;
    } catch {
      setApiStatus({
        state: 'offline',
        label: 'API Offline',
        detail: 'Backend connection unavailable. System data could not be loaded.',
        checkedAt: checkTime.toISOString(),
        attemptCount,
        endpoint: formatEndpoint(apiBaseUrl),
        message: 'Backend connection unavailable. System data could not be loaded.',
      });
      setBackendError('Backend connection unavailable. System data could not be loaded.');
      return false;
    }
  }, [apiAccessCode, apiBaseUrl, apiFetch, formatClockTime, formatEndpoint, hasAccess, setBackendError]);

  return { apiStatus, setApiStatus, checkApiHealth };
}
