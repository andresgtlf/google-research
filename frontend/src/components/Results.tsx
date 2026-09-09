import DocumentFormatSummary from "./DocumentFormatSummary";
import { useMemo, useState } from "react";
import { fileUrl } from "../api";
import type { Job } from "../types";
import { buttonClasses } from "./Button";
import { CaretDownIcon, DownloadSimpleIcon, InfoIcon } from "./Icon";
import EvidenceSourceStatus from "./EvidenceSourceStatus";
import Markdown from "./Markdown";
import ResultsEvidenceTable from "./ResultsEvidenceTable";
import {
  CitationCheckCard,
  getPaywalledFollowUpSummary,
  PaywalledFollowUpCard,
} from "./ResultsEnrichment";
import ResultsSectionNav from "./ResultsSectionNav";
import { extractHeadings } from "../lib/reportHeadings";

interface ResultsProps {
  job: Job;
}

// Starting a new analysis lives in the header ("Start over") only. A second
// button here meant two differently worded controls for one action.
export default function Results({ job }: ResultsProps) {
  const sections = job.result.sections;
  const extraction = job.result.extraction;
  const files = job.result.files ?? {};
  const reportMarkdown = job.result.report_markdown ?? "";
  const parseWarnings = sections?.parse_warnings ?? [];
  const enrichment = sections?.enrichment;
  const enrichmentNotes = enrichment?.enrichment_notes ?? [];

  const table = sections?.evidence_table;

  // The report is the artifact the reviewer came for, and its section nav
  // lives inside this region, so it opens expanded. Collapsing it by default
  // hid a 28k-character report behind a caret and left the nav unrendered.
  const [showFull, setShowFull] = useState(true);

  const headings = useMemo(() => extractHeadings(reportMarkdown), [reportMarkdown]);

  // Counting the entries lets the summary bar point at this section without
  // dumping its full text (often thousands of words, plus a long source
  // list) above the report itself.
  const paywalledCount = useMemo(() => {
    const body = sections?.paywalled ?? "";
    return (body.match(/(^|\n)\s*[-*]\s+\*\*Title/gi) || []).length;
  }, [sections?.paywalled]);
  const paywalledSummary = getPaywalledFollowUpSummary(
    sections?.paywalled ?? "",
    paywalledCount,
    enrichment,
  );
  // A fallback paywalled list can exist without a database query, so the
  // credit follows an actual enrichment result instead of the fallback.
  const showPaywalledAttribution =
    paywalledSummary.shouldRender && paywalledSummary.usesEnrichment;

  return (
    <div className="space-y-6" onClick={(event) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const href = target.closest("a")?.getAttribute("href");
      if (!href || !/^#(?:ref-|cite-ref-|references$)/.test(href)) return;
      event.preventDefault();
      setShowFull(true);
      requestAnimationFrame(() => {
        const destination = document.getElementById(href.slice(1));
        destination?.scrollIntoView({ behavior: "smooth", block: "start" });
        destination?.focus({ preventScroll: true });
      });
    }}>
      {/* Top summary bar: identity, status, downloads. Moved to the top so
          the two most action-relevant items (download, know what to chase
          manually) never require scrolling past the whole report. */}
      <div className="rounded-lg border-l-4 border-[var(--color-accent)] bg-[var(--color-surface-1)] p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-display">{extraction?.organization || "Research report"}</h2>
            <p className="mt-1 text-body text-[var(--color-text-secondary)]">
              {extraction?.project_title}
              {extraction?.country ? ` · ${extraction.country}` : ""}
            </p>
          </div>
          <div className="text-caption text-[var(--color-text-tertiary)]">
            Saved {new Date(job.created_at).toLocaleDateString()} · Engine: <span className="text-mono-data">{job.model}</span>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-3">
          {files.markdown && (
            <a href={fileUrl(job.id, "md")} className={buttonClasses("primary")}>
              <DownloadSimpleIcon size={16} />
              Download markdown
            </a>
          )}
          {files.pdf && (
            <a href={fileUrl(job.id, "pdf")} className={buttonClasses("secondary")}>
              <DownloadSimpleIcon size={16} />
              Download PDF
            </a>
          )}
          {headings.some((heading) => heading.id === "references") && (
            <a href="#references" className={buttonClasses("secondary")}>References</a>
          )}
          {files.json && (
            <a href={fileUrl(job.id, "json")} className={buttonClasses("secondary")}>
              <DownloadSimpleIcon size={16} /> Download research data
            </a>
          )}
          {paywalledSummary.shouldRender && (
            <a
              href="#papers-to-retrieve"
              className="ml-auto self-center text-caption font-medium text-[var(--color-info-text)] underline-offset-2 hover:underline"
            >
              {paywalledSummary.linkLabel}
            </a>
          )}
        </div>
      </div>

      <DocumentFormatSummary extraction={job.result.extraction} />
      <EvidenceSourceStatus status={job.evidence_status} terminal />

      {parseWarnings.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg bg-[var(--color-surface-2)] px-4 py-2.5 text-caption text-[var(--color-text-secondary)]">
          <InfoIcon size={14} className="mt-0.5 shrink-0" />
          <span>{parseWarnings.join(" ")}</span>
        </div>
      )}

      {enrichmentNotes.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg bg-[var(--color-surface-2)] px-4 py-2.5 text-caption text-[var(--color-text-secondary)]">
          <InfoIcon size={14} className="mt-0.5 shrink-0" />
          <span className="min-w-0 break-words">{enrichmentNotes.join(" ")}</span>
        </div>
      )}

      {/* Reading order follows how a grant reviewer works: the verdict, then
          the evidence behind it, then the full document, then the manual
          follow-up list. The paywalled section runs to thousands of words and
          a long source list, so it sits last and closed, reachable from the
          link in the summary bar above. */}
      {sections?.conclusions && (
        <div className="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] p-6">
          <Markdown headingIds={false}>{sections.conclusions}</Markdown>
        </div>
      )}

      {table && (
        <div className="rounded-lg bg-[var(--color-surface-1)] p-4">
          <h3 className="mb-3 text-h3">Evidence digest</h3>
          <ResultsEvidenceTable rows={table} />
        </div>
      )}

      {/* Full report: two-region layout, sticky section nav built from this
          document's own headings, prose capped at 72ch (index.css
          .report-md), tables escape that measure via .report-table-wrapper. */}
      <div className="rounded-lg bg-[var(--color-surface-1)] p-6">
        <button
          type="button"
          aria-expanded={showFull}
          onClick={() => setShowFull((s) => !s)}
          className="flex w-full items-center justify-between text-left"
        >
          <h3 className="text-h3">Full research report</h3>
          <CaretDownIcon
            size={18}
            className={`text-[var(--color-text-tertiary)] transition-transform duration-150 ${showFull ? "rotate-180" : ""}`}
          />
        </button>
        {showFull && reportMarkdown && (
          <div className="mt-4 border-t border-[var(--color-border-subtle)] pt-4">
            <div className="lg:flex lg:items-start lg:gap-8">
              <ResultsSectionNav headings={headings} />
              <div className="min-w-0 flex-1 break-words">
                <Markdown>{reportMarkdown}</Markdown>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* These are follow-up and diligence details rather than report
          conclusions, so they stay after the canonical full-report render. */}
      <PaywalledFollowUpCard
        paywalledMarkdown={sections?.paywalled ?? ""}
        paywalledCount={paywalledCount}
        enrichment={enrichment}
        showAttribution={showPaywalledAttribution}
      />
      <CitationCheckCard
        enrichment={enrichment}
        showAttribution={!showPaywalledAttribution}
      />
    </div>
  );
}
