import { useRef, useState } from "react";
import { FileArrowUpIcon, FileTextIcon, WarningCircleIcon, XIcon } from "./Icon";

const MAX_BYTES = 50 * 1024 * 1024; // matches backend/main.py MAX_UPLOAD_BYTES

function formatSize(bytes: number): string {
  const kb = bytes / 1024;
  return kb < 1024 ? `${kb.toFixed(1)} KB` : `${(kb / 1024).toFixed(1)} MB`;
}

export default function UploadZone({
  file,
  onFile,
}: {
  file: File | null;
  onFile: (f: File | null) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  function accept(candidate: File | undefined) {
    if (!candidate) return;
    if (!candidate.name.toLowerCase().endsWith(".pdf")) {
      setLocalError("This file isn't a PDF. Upload the concept note as a .pdf and try again.");
      return;
    }
    if (candidate.size > MAX_BYTES) {
      setLocalError(
        "This PDF is larger than 50 MB. Compress it or split it into sections, then upload again."
      );
      return;
    }
    setLocalError(null);
    onFile(candidate);
  }

  if (file) {
    return (
      <div className="flex items-center gap-4 rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] p-4">
        <FileTextIcon size={28} className="shrink-0 text-[var(--color-accent)]" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-body font-medium text-[var(--color-text-primary)]">
            {file.name}
          </div>
          <div className="text-mono-data text-[var(--color-text-secondary)]">
            {formatSize(file.size)} &middot; PDF document
          </div>
        </div>
        <button
          type="button"
          onClick={() => onFile(null)}
          className="shrink-0 rounded-lg px-3 py-1.5 text-caption font-medium text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-primary)]"
        >
          Remove
        </button>
      </div>
    );
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          accept(e.dataTransfer.files[0]);
        }}
        className={`flex w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-12 text-center transition-colors duration-150 ${
          localError
            ? "border-[var(--color-danger)] bg-[var(--color-danger-bg)]"
            : dragging
              ? "scale-[1.005] border-[var(--color-accent)] bg-[var(--color-accent-subtle)]"
              : "border-[var(--color-border-strong)] bg-[var(--color-surface-2)] hover:border-[var(--color-accent)]/40 hover:bg-[var(--color-surface-1)]"
        }`}
      >
        {localError ? (
          <WarningCircleIcon size={40} className="text-[var(--color-danger)]" />
        ) : (
          <FileArrowUpIcon
            size={40}
            className={dragging ? "text-[var(--color-accent)]" : "text-[var(--color-text-secondary)]"}
          />
        )}
        <div className="text-h3 text-[var(--color-text-primary)]">
          Drop your concept note here
        </div>
        <div className="text-body text-[var(--color-text-secondary)]">
          or click to browse. PDF, up to 50 MB.
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => accept(e.target.files?.[0])}
        />
      </button>
      {localError && (
        <div className="mt-1.5 flex items-start gap-1.5 text-caption text-[var(--color-danger-text)]">
          <WarningCircleIcon size={14} className="mt-0.5 shrink-0" />
          <span>{localError}</span>
          <button
            type="button"
            onClick={() => setLocalError(null)}
            className="ml-1 inline-flex shrink-0 items-center text-[var(--color-danger-text)] hover:underline"
          >
            <XIcon size={12} />
          </button>
        </div>
      )}
    </div>
  );
}
