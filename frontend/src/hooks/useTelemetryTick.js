import { useEffect, useState } from 'react';

export default function useTelemetryTick({ hasAccess, cadenceMs }) {
  const [telemetryTick, setTelemetryTick] = useState(0);

  useEffect(() => {
    if (!hasAccess) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      setTelemetryTick((current) => current + 1);
    }, cadenceMs);

    return () => window.clearInterval(intervalId);
  }, [hasAccess, cadenceMs]);

  return { telemetryTick, setTelemetryTick };
}
