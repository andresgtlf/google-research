import { useEffect, useState } from "react";

/** Ticks once a second so callers re-render and can recompute an elapsed
 * duration from a fixed start time. Returns the tick count itself (unused
 * by callers) purely to force the re-render. */
function useTicker(): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  return tick;
}

export interface ElapsedResult {
  totalSeconds: number;
  /** MM:SS, zero-padded, suitable for a tabular-nums mono timer. */
  label: string;
}

/** Derives elapsed time from a fixed ISO start timestamp, re-computed every
 * second. Never drifts from a client-side counter because it always
 * re-derives from `startIso` rather than accumulating. */
export function useElapsed(startIso: string | undefined): ElapsedResult {
  useTicker();
  if (!startIso) return { totalSeconds: 0, label: "00:00" };
  const totalSeconds = Math.max(
    0,
    Math.floor((Date.now() - new Date(startIso).getTime()) / 1000)
  );
  const mm = Math.floor(totalSeconds / 60);
  const ss = totalSeconds % 60;
  const label = `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
  return { totalSeconds, label };
}
