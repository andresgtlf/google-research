import type { ExtractionData } from "../types";

export default function DocumentFormatSummary({ extraction }: { extraction?: ExtractionData }) {
  if (!extraction?.source_format) return null;
  const label = extraction.source_format === "next_ladder_intake" ? "Next Ladder intake survey" : extraction.source_format === "concept_note" ? "GitLab concept note" : "Format uncertain — review needed";
  const fields = Object.entries(extraction.intake ?? {}).filter(([, value]) => Array.isArray(value) ? value.length : value);
  return <div className="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] p-4">
    <p className="text-body font-medium">Document format: {label}</p>
    {extraction.format_reason && <p className="mt-1 text-caption text-[var(--color-text-secondary)]">{extraction.format_reason}</p>}
    {extraction.format_confidence === "low" && <p className="mt-2 text-caption">Check the fields and research prompt. To change formats, start over and select the intended format beside the upload area.</p>}
    {extraction.source_format === "next_ladder_intake" && fields.length > 0 && <details className="mt-3">
      <summary className="cursor-pointer text-label">Intake claims and model inputs</summary>
      <p className="my-2 text-caption">Reported by the source; not independently verified.</p>
      <dl className="space-y-3 text-caption">{fields.map(([key, value]) => <div key={key}>
        <dt className="font-medium capitalize">{key.replaceAll("_", " ")}</dt>
        <dd className="mt-1 whitespace-pre-wrap">{Array.isArray(value) ? value.join("\n") : value}</dd>
      </div>)}</dl>
    </details>}
  </div>;
}
