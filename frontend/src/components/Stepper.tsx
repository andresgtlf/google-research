import { CheckIcon } from "./Icon";

export const STEP_LABELS = ["Upload", "Review", "Progress", "Report"] as const;

type StepState = "done" | "active" | "upcoming";

function stateFor(index: number, currentIndex: number): StepState {
  if (index < currentIndex) return "done";
  if (index === currentIndex) return "active";
  return "upcoming";
}

const BADGE_CLASSES: Record<StepState, string> = {
  done: "bg-[var(--color-accent)] text-white",
  active:
    "border-2 border-[var(--color-accent)] text-[var(--color-accent)] bg-[var(--color-accent-subtle)]",
  upcoming:
    "border border-[var(--color-border-strong)] text-[var(--color-text-tertiary)] bg-[var(--color-surface-1)]",
};

const LABEL_CLASSES: Record<StepState, string> = {
  done: "text-[var(--color-text-primary)]",
  active: "font-semibold text-[var(--color-text-primary)]",
  upcoming: "text-[var(--color-text-tertiary)]",
};

/**
 * Persistent top stepper, part of the shell that never moves between
 * steps. Connectors use `flex-1` (not a fixed width) and the row scrolls
 * horizontally as a fallback, which is the fix for the audit bug where
 * fixed `w-14` connectors plus `mx-3` overflowed the viewport around
 * 375px with no way to see the remaining steps.
 */
export default function Stepper({ currentIndex }: { currentIndex: number }) {
  return (
    <div className="w-full border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-0)]">
      <div className="mx-auto max-w-[1200px] px-4 py-4 sm:px-6">
        <ol className="flex items-center justify-between gap-1 sm:justify-start sm:gap-2">
          {STEP_LABELS.map((label, index) => {
            const state = stateFor(index, currentIndex);
            const isLast = index === STEP_LABELS.length - 1;
            return (
              <li key={label} className="flex shrink-0 items-center">
                <div
                  className="flex cursor-default flex-col items-center gap-1 text-label sm:flex-row sm:gap-2"
                  aria-current={state === "active" ? "step" : undefined}
                >
                  <span
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-caption font-medium transition-colors duration-150 ${BADGE_CLASSES[state]}`}
                  >
                    {state === "done" ? <CheckIcon size={12} /> : index + 1}
                  </span>
                  <span className={`whitespace-nowrap text-[11px] sm:text-sm ${LABEL_CLASSES[state]}`}>
                    {label}
                  </span>
                </div>
                {!isLast && (
                  <div
                    className={`mx-3 hidden h-px min-w-[1.5rem] flex-1 sm:block transition-colors duration-150 ${
                      index < currentIndex
                        ? "bg-[var(--color-accent)]"
                        : "bg-[var(--color-border-subtle)]"
                    }`}
                  />
                )}
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
