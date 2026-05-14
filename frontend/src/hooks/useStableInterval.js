import { useEffect, useRef } from "react";

export default function useStableInterval(callback, delayMs, enabled = true) {
  const callbackRef = useRef(callback);

  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  useEffect(() => {
    if (!enabled || !Number.isFinite(delayMs) || delayMs <= 0) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      callbackRef.current();
    }, delayMs);
    return () => window.clearInterval(intervalId);
  }, [delayMs, enabled]);
}
