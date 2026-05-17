import { useCallback, useRef, useState } from 'react';

export default function useFacilitySystems({
  hasAccess,
  apiAccessCode,
  apiFetch,
  apiStatusState,
  buildProtectedRequestMessage,
  normalizeErrorMessage,
  fallbackSystems,
  uploadStateView,
  apiConfigWarning,
  setBackendError,
}) {
  const [systems, setSystems] = useState(fallbackSystems);
  const [systemsState, setSystemsState] = useState('loading');
  const [intelligenceStatus, setIntelligenceStatus] = useState(uploadStateView.buildEmptyIntelligenceStatus());
  const facilitySystemsFetchDisabledRef = useRef(false);

  const loadFacilitySystems = useCallback(async () => {
    if (!hasAccess || facilitySystemsFetchDisabledRef.current) {
      return false;
    }

    try {
      const response = await apiFetch('/api/facility/systems', { accessCode: apiAccessCode });
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          throw new Error(await buildProtectedRequestMessage(response));
        }
        throw new Error(`Unexpected response: ${response.status}`);
      }

      const payload = await response.json();
      if (!Array.isArray(payload.systems)) {
        throw new Error('Facility systems payload was incomplete.');
      }

      setSystems(payload.systems);
      setIntelligenceStatus(payload.intelligence_status ?? uploadStateView.buildEmptyIntelligenceStatus());
      setSystemsState('ready');
      setBackendError(apiConfigWarning);
      return true;
    } catch (error) {
      const normalizedMessage = normalizeErrorMessage(error?.message ?? error);
      const lowerMessage = String(normalizedMessage || '').toLowerCase();
      if (
        lowerMessage.includes('404')
        || lowerMessage.includes('unexpected response')
        || lowerMessage.includes('failed to fetch')
        || lowerMessage.includes('networkerror')
        || lowerMessage.includes('cors')
      ) {
        facilitySystemsFetchDisabledRef.current = true;
      }
      setSystems(fallbackSystems);
      setIntelligenceStatus(uploadStateView.buildEmptyIntelligenceStatus());
      setSystemsState('fallback');
      setBackendError((current) => {
        if (normalizedMessage === 'Session expired. Refresh workspace.') {
          return normalizedMessage;
        }
        if (apiStatusState === 'offline') {
          return 'Backend connection unavailable. System data could not be loaded.';
        }
        return current || apiConfigWarning;
      });
      return false;
    }
  }, [apiAccessCode, apiConfigWarning, apiFetch, apiStatusState, buildProtectedRequestMessage, fallbackSystems, hasAccess, normalizeErrorMessage, setBackendError, uploadStateView]);

  const resetFacilitySystemsFetchDisabled = useCallback(() => {
    facilitySystemsFetchDisabledRef.current = false;
  }, []);

  return {
    systems,
    systemsState,
    intelligenceStatus,
    setSystems,
    setSystemsState,
    setIntelligenceStatus,
    loadFacilitySystems,
    resetFacilitySystemsFetchDisabled,
  };
}
