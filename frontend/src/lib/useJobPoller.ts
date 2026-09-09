import { useEffect, useRef } from "react";
import { ApiError, fetchJob } from "../api";
import type { Job } from "../types";

const TERMINAL_STATUSES = new Set(["completed", "failed", "interrupted"]);
const MAX_CONSECUTIVE_FAILURES = 5;
const GRACE_POLLS_FOR_404 = 2;

interface UseJobPollerOptions {
  /** Job to poll. Polling is inactive while this is null. */
  jobId: string | null;
  /** Set to false once the job reaches a terminal state, or to pause. */
  active: boolean;
  intervalMs?: number;
  onUpdate: (job: Job) => void;
  /** Called once, the first time a terminal status is observed. */
  onTerminal: (job: Job) => void;
  /** Called after too many consecutive failures to keep polling. */
  onFatalError: (message: string) => void;
}

/**
 * Self-scheduling setTimeout poll loop (never setInterval, so there is no
 * risk of overlapping in-flight requests piling up). Tolerates a run of
 * transient failures instead of failing a healthy job on the first blip,
 * and gives a freshly-created job id a short grace period before a 404
 * counts against it (the id can be persisted to localStorage and re-polled
 * a beat before the server has fully registered it after a restart).
 */
export function useJobPoller({
  jobId,
  active,
  intervalMs = 3500,
  onUpdate,
  onTerminal,
  onFatalError,
}: UseJobPollerOptions): void {
  // Keep the latest callbacks in refs so the effect below does not need to
  // restart the poll loop just because a parent re-render created new
  // inline function identities.
  const callbacksRef = useRef({ onUpdate, onTerminal, onFatalError });
  callbacksRef.current = { onUpdate, onTerminal, onFatalError };

  useEffect(() => {
    if (!active || !jobId) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let consecutiveFailures = 0;
    let pollAttempt = 0;

    async function poll() {
      pollAttempt += 1;
      try {
        const job = await fetchJob(jobId as string);
        if (cancelled) return;
        consecutiveFailures = 0;
        callbacksRef.current.onUpdate(job);
        if (TERMINAL_STATUSES.has(job.status)) {
          callbacksRef.current.onTerminal(job);
          return; // stop the loop, terminal state reached
        }
      } catch (error) {
        if (cancelled) return;
        const is404 = error instanceof ApiError && error.status === 404;
        const withinGracePeriod = is404 && pollAttempt <= GRACE_POLLS_FOR_404;
        if (!withinGracePeriod) {
          consecutiveFailures += 1;
        }
        if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
          callbacksRef.current.onFatalError(
            error instanceof Error ? error.message : "Could not reach the server"
          );
          return; // stop the loop
        }
      }
      if (cancelled) return;
      const backoff =
        consecutiveFailures > 0
          ? Math.min(intervalMs * (1 + consecutiveFailures), intervalMs * 4)
          : intervalMs;
      timer = setTimeout(poll, backoff);
    }

    // Poll right away so a rehydrated/resumed job shows fresh status
    // immediately instead of waiting a full interval.
    timer = setTimeout(poll, 0);

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId, active, intervalMs]);
}
