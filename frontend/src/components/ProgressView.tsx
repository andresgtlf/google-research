import DocumentFormatSummary from "./DocumentFormatSummary";
import { useEffect, useRef } from "react";
import type { Job } from "../types";
import EvidenceSourceStatus from "./EvidenceSourceStatus";
import { useElapsed } from "../lib/useElapsed";

const LONG_TAIL_THRESHOLD_SECONDS = 25 * 60;

interface ProgressViewProps {
  phase: "extracting" | "researching";
  job: Job | null;
  providerLabel: string;
}

/**
 * The highest-stakes screen in the app (5 to 20+ minutes of waiting). No
 * numeric percentage exists anywhere in the backend, so this deliberately
 * never fakes one: an indeterminate shimmer bar (evidence of life, not a
 * measurement), a real elapsed timer, the backend's own event log, and a
 * skeleton preview of the results screen's shape.
 */
export default function ProgressView({ phase, job, providerLabel }: ProgressViewProps) {
  const { label: elapsedLabel, totalSeconds } = useElapsed(job?.created_at);
  const events = job?.events ?? [];
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const log = logEndRef.current?.parentElement;
    if (log) log.scrollTop = log.scrollHeight;
  }, [events.length]);

  const heading =
    phase === "extracting"
      ? job?.evidence_status?.state === "searching" ? "Finding relevant papers" : "Preparing the evidence review"
      : `Running research with ${providerLabel}`;

  const introCopy =
    phase === "extracting"
      ? "Reading the document, then searching scholarly sources for relevant papers. The source search may take a few minutes."
      : "Research in progress. This typically takes 5 to 20 minutes depending on the provider and prompt length. You can leave this tab open.";

  return (
    <div className="space-y-6">
      <DocumentFormatSummary extraction={job?.result.extraction} />
      <EvidenceSourceStatus status={job?.evidence_status} />
      <div className="rounded-lg bg-[var(--color-surface-1)] border border-[var(--color-border-subtle)] p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-h3">{heading}</h2>
            <p className="mt-1 text-body text-[var(--color-text-secondary)]">{introCopy}</p>
          </div>
          <div className="shrink-0 text-right">
            <div className="text-label text-[var(--color-text-secondary)]">Elapsed</div>
            <div className="text-mono-data text-lg font-medium">{elapsedLabel}</div>
          </div>
        </div>

        <div
          className="progress-shimmer relative mt-5 h-1.5 overflow-hidden rounded-full bg-[var(--color-surface-2)]"
          role="progressbar"
          aria-label={phase === "extracting" ? "Extracting" : "Researching"}
        >
          <div className="h-full w-1/3 rounded-full bg-[var(--color-accent-mid)]" />
        </div>

        {totalSeconds > LONG_TAIL_THRESHOLD_SECONDS && (
          <p className="mt-4 rounded-lg bg-[var(--color-warning-bg)] px-3 py-2 text-caption text-[var(--color-warning-text)]">
            This is taking longer than usual. It's still running. You can leave
            this tab open or come back later, nothing needs to be resubmitted.
          </p>
        )}

        {events.length > 0 && (
          <div className="mt-5 max-h-80 overflow-y-auto rounded-lg bg-[var(--color-surface-2)] p-4">
            <ol className="space-y-2">
              {events.map((e, i) => (
                <li key={`${e.time}-${i}`} className="log-line-in text-mono-data">
                  <span className="text-[var(--color-text-tertiary)]">
                    {new Date(e.time).toLocaleTimeString()}
                  </span>{" "}
                  <span className="text-[var(--color-text-primary)]">{e.message}</span>
                </li>
              ))}
            </ol>
            <div ref={logEndRef} />
          </div>
        )}
      </div>

      {/* Skeleton preview of the results screen's shape, so the wait has a
          visual preview of what's coming rather than just a log. */}
      <div className="rounded-lg border border-[var(--color-border-subtle)] p-4 opacity-60">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[16rem_1fr]">
          <div className="hidden space-y-2 lg:block">
            <div className="h-3 w-24 animate-pulse rounded bg-[var(--color-surface-2)]" />
            <div className="h-3 w-32 animate-pulse rounded bg-[var(--color-surface-2)]" />
            <div className="h-3 w-28 animate-pulse rounded bg-[var(--color-surface-2)]" />
          </div>
          <div className="space-y-3">
            <div className="h-4 w-2/3 animate-pulse rounded bg-[var(--color-surface-2)]" />
            <div className="h-3 w-full animate-pulse rounded bg-[var(--color-surface-2)]" />
            <div className="h-3 w-full animate-pulse rounded bg-[var(--color-surface-2)]" />
            <div className="h-3 w-5/6 animate-pulse rounded bg-[var(--color-surface-2)]" />
          </div>
        </div>
      </div>
    </div>
  );
}
