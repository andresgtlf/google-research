import Button from "./Button";
import { ArrowClockwiseIcon } from "./Icon";

interface ResearchErrorCardProps {
  message: string | null;
  /** True when there is a preserved prompt to return to (spec: retry must
   * not discard the reviewer's edited prompt). */
  canRetryWithPrompt: boolean;
  onRetry: () => void;
  onReset: () => void;
}

/** Shown when a research job fails or is interrupted by a server restart.
 * "Retry" returns to the prompt-review step with the same prompt still
 * filled in rather than discarding the reviewer's edits. */
export default function ResearchErrorCard({
  message,
  canRetryWithPrompt,
  onRetry,
  onReset,
}: ResearchErrorCardProps) {
  return (
    <div className="rounded-lg border-l-4 border-[var(--color-danger)] bg-[var(--color-danger-bg)] p-6">
      <h2 className="text-h3 text-[var(--color-danger-text)]">Research did not complete</h2>
      <p className="mt-2 text-body text-[var(--color-danger-text)]">{message}</p>
      <div className="mt-4 flex flex-wrap gap-3">
        {canRetryWithPrompt && (
          <Button variant="primary" onClick={onRetry}>
            <ArrowClockwiseIcon size={16} />
            Retry with this prompt
          </Button>
        )}
        <Button variant="secondary" onClick={onReset}>
          Start over
        </Button>
      </div>
    </div>
  );
}
