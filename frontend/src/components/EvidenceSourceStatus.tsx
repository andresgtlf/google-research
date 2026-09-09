import type { EvidenceStatus } from "../types";

const LABELS: Record<EvidenceStatus["state"], string> = {
  waiting: "Up next", searching: "Searching", complete: "Search complete",
  partial: "Partial results", unavailable: "Unavailable", disabled: "Not enabled",
};

export default function EvidenceSourceStatus({ status, terminal = false }: {
  status?: EvidenceStatus; terminal?: boolean;
}) {
  if (!status?.state || !(status.state in LABELS)) return null;
  const interrupted = terminal && (status.state === "waiting" || status.state === "searching");
  const busy = (status.state === "searching" || Boolean(status.activity)) && !terminal;
  const warning = status.state === "partial" || status.state === "unavailable" || interrupted;
  return (
    <section aria-label="OpenAlex evidence search" aria-live="polite" className="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-h3">OpenAlex · Scholarly papers</h3>
        <span className={`rounded-full px-3 py-1 text-caption ${warning ? "bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]" : "bg-[var(--color-surface-2)] text-[var(--color-text-secondary)]"}`}>
          {busy && <span aria-hidden="true" className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-[var(--color-accent)]" />}
          {interrupted ? "Not completed" : status.activity && !terminal ? "Checking citations and access" : status.reused ? `Saved snapshot · ${LABELS[status.state]}` : LABELS[status.state]}
        </span>
      </div>
      <p className="mt-2 text-body text-[var(--color-text-secondary)]">
        {interrupted ? "This run ended before the OpenAlex search completed." : status.message}
      </p>
      {status.activity && !terminal && <p className="mt-2 text-caption font-medium">{status.activity}</p>}
      {status.retrieved_at && <p className="mt-2 text-caption text-[var(--color-text-tertiary)]">Evidence retrieved {new Date(status.retrieved_at).toLocaleString()}</p>}
    </section>
  );
}
