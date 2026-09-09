import type { ReactNode } from "react";
import type { JobStatus } from "../types";

type Tone = "success" | "info" | "danger" | "warning" | "neutral";

const TONE_CLASSES: Record<Tone, string> = {
  success: "bg-[var(--color-success-bg)] text-[var(--color-success-text)]",
  info: "bg-[var(--color-info-bg)] text-[var(--color-info-text)]",
  danger: "bg-[var(--color-danger-bg)] text-[var(--color-danger-text)]",
  warning: "bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]",
  neutral: "bg-[var(--color-surface-2)] text-[var(--color-text-secondary)]",
};

export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-caption font-medium ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}

const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Complete",
  failed: "Failed",
  interrupted: "Interrupted",
};

const STATUS_TONE: Record<JobStatus, Tone> = {
  queued: "neutral",
  running: "info",
  completed: "success",
  failed: "danger",
  interrupted: "danger",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  return <Badge tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Badge>;
}
