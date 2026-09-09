import type { ProviderInfo, ResearchMode, DocumentFormat } from "../types";
import Button from "./Button";
import ProviderPicker from "./ProviderPicker";
import UploadZone from "./UploadZone";

interface ConfigureStepProps {
  documentFormat: DocumentFormat;
  onDocumentFormat: (value: DocumentFormat) => void;
  file: File | null;
  onFile: (f: File | null) => void;
  mode: ResearchMode;
  onMode: (m: ResearchMode) => void;
  providerId: string;
  tier: string;
  onProviderSelect: (id: string) => void;
  onTier: (tier: string) => void;
  providers: ProviderInfo[];
  providersError: string | null;
  onRetryProviders: () => void;
  extractError: string | null;
  onDismissExtractError: () => void;
  hydrationNotice: string | null;
  onStart: () => void;
  startDisabledReason: string | null;
}

const MODE_OPTIONS: readonly [ResearchMode, string, string][] = [
  ["standard", "Standard", "Run research automatically"],
  ["customized", "Customized", "Review and edit the prompt first"],
];

/** Step 1: upload plus the choices needed before a run starts. The
 * dropzone is the first interactive element in the DOM (spec's "primary
 * action first" rule) - there is no competing sidebar of intro copy above
 * it, which is the audit bug's root cause fixed at the source rather than
 * patched with responsive order utilities. */
export default function ConfigureStep({
  file,
  onFile,
  documentFormat,
  onDocumentFormat,
  mode,
  onMode,
  providerId,
  tier,
  onProviderSelect,
  onTier,
  providers,
  providersError,
  onRetryProviders,
  extractError,
  onDismissExtractError,
  hydrationNotice,
  onStart,
  startDisabledReason,
}: ConfigureStepProps) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-display">Research for concept notes and intake surveys</h1>
        <p className="mt-1 text-body text-[var(--color-text-secondary)]">
          Upload a GitLab Foundation concept note or Next Ladder intake survey.
          The agent researches the financial-impact pathways and links the evidence.
        </p>
      </div>

      {hydrationNotice && (
        <div className="rounded-lg bg-[var(--color-info-bg)] px-4 py-2.5 text-caption text-[var(--color-info-text)]">
          {hydrationNotice}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-[1fr_200px]">
        <UploadZone file={file} onFile={onFile} />
        <div>
          <label htmlFor="document-format" className="mb-2 block text-label">Document format</label>
          <select id="document-format" value={documentFormat} onChange={e => onDocumentFormat(e.target.value as DocumentFormat)} className="w-full rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] p-3 text-body">
            <option value="auto">Detect automatically</option>
            <option value="concept_note">GitLab concept note</option>
            <option value="next_ladder_intake">Next Ladder intake</option>
          </select>
          <p className="mt-2 text-caption text-[var(--color-text-secondary)]">Detection uses document content. Uncertain matches pause for review before research.</p>
        </div>
      </div>

      {extractError && (
        <div className="rounded-r-lg border-l-4 border-[var(--color-danger)] bg-[var(--color-danger-bg)] p-4">
          <h3 className="text-h3 text-[var(--color-danger-text)]">Extraction failed</h3>
          <p className="mt-1 text-body text-[var(--color-danger-text)]">{extractError}</p>
          <Button variant="secondary" className="mt-3" onClick={onDismissExtractError}>
            Try again
          </Button>
        </div>
      )}

      {providersError && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--color-warning)]/25 bg-[var(--color-warning-bg)] px-4 py-3 text-caption text-[var(--color-warning-text)]">
          <span>Could not load research engines: {providersError}</span>
          <Button variant="secondary" onClick={onRetryProviders}>
            Retry
          </Button>
        </div>
      )}

      <div className="rounded-lg bg-[var(--color-surface-1)] p-6">
        <div className="mb-2 text-label text-[var(--color-text-secondary)]">Research mode</div>
        <div className="flex gap-3">
          {MODE_OPTIONS.map(([id, label, desc]) => (
            <button
              key={id}
              type="button"
              onClick={() => onMode(id)}
              className={`flex-1 rounded-lg border p-3 text-left transition-colors duration-150 ${
                mode === id
                  ? "border-[var(--color-accent)] bg-[var(--color-accent-subtle)]"
                  : "border-[var(--color-border-subtle)] hover:border-[var(--color-border-strong)]"
              }`}
            >
              <div className="text-body font-medium">{label}</div>
              <div className="text-caption text-[var(--color-text-secondary)]">{desc}</div>
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-lg bg-[var(--color-surface-1)] p-6">
        <ProviderPicker
          providers={providers}
          selected={providerId}
          tier={tier}
          onSelect={onProviderSelect}
          onTier={onTier}
        />
      </div>

      <Button
        variant="primary"
        className="w-full"
        onClick={onStart}
        disabled={Boolean(startDisabledReason)}
      >
        {startDisabledReason ?? "Start analysis"}
      </Button>
    </div>
  );
}
