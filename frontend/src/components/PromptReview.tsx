import type { ExtractionData } from "../types";
import Button from "./Button";

interface PromptReviewProps {
  extraction: ExtractionData | undefined;
  prompt: string;
  onPromptChange: (prompt: string) => void;
  onRun: () => void;
  onReset: () => void;
}

function wordCount(text: string): number {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

/**
 * The `grid-cols-2` here previously had no responsive breakpoint, so the
 * extracted-data pairs got squeezed into unreadable narrow columns on
 * mobile. Fixed below with `grid-cols-1 sm:grid-cols-2`.
 */
export default function PromptReview({
  extraction,
  prompt,
  onPromptChange,
  onRun,
  onReset,
}: PromptReviewProps) {
  return (
    <div className="space-y-6">
      {extraction && (
        <div className="rounded-lg border-l-4 border-[var(--color-accent)] bg-[var(--color-surface-1)] p-6">
          <h3 className="mb-3 text-h3">Extracted data</h3>
          <div className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-body sm:grid-cols-2">
            <div>
              <span className="font-medium">Organization:</span>{" "}
              {extraction.organization || "Not stated"}
            </div>
            <div>
              <span className="font-medium">Country:</span>{" "}
              {extraction.country || "Not stated"}
              {extraction.region ? ` (${extraction.region})` : ""}
            </div>
            <div className="sm:col-span-2">
              <span className="font-medium">Project:</span>{" "}
              {extraction.project_title || "Not stated"}
            </div>
            {extraction.primary_research_question && (
              <div className="mt-1 rounded-lg bg-[var(--color-accent-subtle)] p-3 text-caption leading-relaxed sm:col-span-2">
                <span className="font-medium">Primary research question: </span>
                {extraction.primary_research_question}
              </div>
            )}
          </div>
        </div>
      )}

      <div>
        <div className="mb-2 flex items-baseline justify-between">
          <label htmlFor="research-prompt" className="text-label text-[var(--color-text-secondary)]">
            Research prompt
          </label>
          <span className="text-caption text-[var(--color-text-tertiary)]">
            {wordCount(prompt)} words
          </span>
        </div>
        <p className="mb-2 text-caption text-[var(--color-text-tertiary)]">
          Edit this prompt before running research. Changes here directly
          change what the model investigates. The paywalled-papers section is
          included by default, keep it if you want the manual retrieval list.
        </p>
        {!prompt && (
          <p className="mb-2 text-caption text-[var(--color-warning-text)]">
            Extraction did not return a prompt. Write one manually or re-upload.
          </p>
        )}
        <textarea
          id="research-prompt"
          value={prompt}
          onChange={(e) => onPromptChange(e.target.value)}
          rows={20}
          className="w-full min-h-[320px] resize-y rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] p-4 text-mono-data leading-relaxed focus:border-[var(--color-accent)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/15"
        />
      </div>

      <div className="flex flex-wrap gap-3">
        <Button variant="primary" onClick={onRun} disabled={!prompt.trim()}>
          Run research
        </Button>
        <Button variant="secondary" onClick={onReset}>
          Start over
        </Button>
      </div>
    </div>
  );
}
