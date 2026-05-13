import { useMemo } from 'react';

export default function useDriftHistory({ telemetryTick, relationshipRows, driftRows, formatClockTime, setDriftHistory }) {
  const driftFingerprint = useMemo(() => {
    const relationshipMagnitude = (relationshipRows ?? [])
      .map((row) => Number(row?.pair_weight ?? row?.change ?? 0))
      .filter((value) => Number.isFinite(value))
      .reduce((sum, value) => sum + Math.abs(value), 0);
    const driftMagnitude = (driftRows ?? [])
      .map((row) => Number(row?.absolute_change ?? 0))
      .filter((value) => Number.isFinite(value))
      .reduce((sum, value) => sum + Math.abs(value), 0);

    return Number((relationshipMagnitude + driftMagnitude).toFixed(3));
  }, [relationshipRows, driftRows]);

  useMemo(() => {
    const stamp = formatClockTime(new Date());
    const baselineDistance = driftFingerprint;

    setDriftHistory((current) => {
      const previousTone = current.length > 0 ? current[current.length - 1].tone : 'nominal';
      const previousRank = previousTone === 'unstable' || previousTone === 'elevated' ? 2 : previousTone === 'review' ? 1 : 0;
      const escalateToReview = baselineDistance >= 0.16;
      const escalateToSeparation = baselineDistance >= 0.36;
      const deescalateToReview = baselineDistance <= 0.31;
      const deescalateToStable = baselineDistance <= 0.11;

      let smoothedTone = previousTone;
      if (previousRank <= 0) {
        smoothedTone = escalateToReview ? 'review' : 'nominal';
      } else if (previousRank === 1) {
        if (escalateToSeparation) {
          smoothedTone = 'elevated';
        } else if (deescalateToStable) {
          smoothedTone = 'nominal';
        } else {
          smoothedTone = 'review';
        }
      } else {
        smoothedTone = deescalateToReview ? 'review' : 'elevated';
      }

      const velocity = current.length > 0 ? Number((baselineDistance - current[current.length - 1].distance).toFixed(3)) : 0;
      const acceleration = current.length > 1 ? Number((velocity - current[current.length - 1].velocity).toFixed(3)) : 0;
      return [...current, { stamp, distance: baselineDistance, velocity, acceleration, tone: smoothedTone }].slice(-48);
    });
  }, [driftFingerprint, formatClockTime, setDriftHistory, telemetryTick]);

  return driftFingerprint;
}
