import type { JobStatus } from "../types";
import { StatusBadge } from "./Badge";
import Button from "./Button";

interface HeaderProps {
  stepLabel: string;
  stepIndex: number;
  totalSteps: number;
  jobStatus?: JobStatus;
  showReset: boolean;
  onReset: () => void;
}

/**
 * Full-bleed brand bar. Never re-mounts or changes width/position between
 * steps (spec Section 5's anti-jump rule): only the text inside changes.
 * `flex-wrap` plus `min-w-0`/`truncate` on the right-hand group fixes the
 * audit bug where a narrow viewport clipped this row instead of wrapping.
 */
export default function Header({
  stepLabel,
  stepIndex,
  totalSteps,
  jobStatus,
  showReset,
  onReset,
}: HeaderProps) {
  return (
    <header className="w-full border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]">
      <div className="mx-auto flex min-h-16 max-w-[1200px] flex-wrap items-center justify-between gap-x-6 gap-y-2 px-6 py-3">
        <div className="flex min-w-0 shrink-0 items-center gap-3">
          <img
            src="/gtlf.webp"
            alt="GitLab Foundation"
            className="h-8 w-auto shrink-0"
          />
          <span className="hidden text-label text-[var(--color-text-secondary)] sm:inline">
            Research
          </span>
        </div>

        <div className="flex min-w-0 items-center gap-3">
          <div className="min-w-0 text-right">
            <div className="truncate text-label text-[var(--color-text-secondary)]">
              Step {stepIndex + 1} of {totalSteps}: {stepLabel}
            </div>
          </div>
          {jobStatus && <StatusBadge status={jobStatus} />}
          {showReset && (
            <Button variant="tertiary" onClick={onReset} className="shrink-0">
              Start over
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}
