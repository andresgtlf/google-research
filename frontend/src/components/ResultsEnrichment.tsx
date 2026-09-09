import { useState, type ReactElement } from "react";
import type { EnrichmentData } from "../types";
import { Badge } from "./Badge";
import { CaretDownIcon } from "./Icon";
import Markdown from "./Markdown";

// Keep this user-facing copy aligned with backend/evidence/attribution.py,
// which is the canonical wording used in exported reports and PDFs.
const EVIDENCE_ATTRIBUTION = {
  intro: "Published research was located and cross-checked using the ",
  econlitName: "Economics Literature Search",
  econlitCredit: " (Paul Goldsmith-Pinkham, Yale School of Management) and ",
  openAlexName: "OpenAlex",
  openAlexCredit: " (OurResearch); the assessment itself is not theirs.",
} as const;

interface PaywalledFollowUpSummary {
  shouldRender: boolean;
  usesEnrichment: boolean;
  resolvedCount: number;
  totalCount: number;
  title: string;
  description: string;
  linkLabel: string;
}

function paperLabel(count: number): string {
  return count === 1 ? "paper" : "papers";
}

function EvidenceAttribution(): ReactElement {
  return (
    <p className="mt-4 break-words text-caption text-[var(--color-text-tertiary)]">
      {EVIDENCE_ATTRIBUTION.intro}
      <a
        href="https://paulgp.com/econlit-pipeline/"
        target="_blank"
        rel="noopener noreferrer"
        className="underline underline-offset-2"
      >
        {EVIDENCE_ATTRIBUTION.econlitName}
      </a>
      {EVIDENCE_ATTRIBUTION.econlitCredit}
      <a
        href="https://openalex.org"
        target="_blank"
        rel="noopener noreferrer"
        className="underline underline-offset-2"
      >
        {EVIDENCE_ATTRIBUTION.openAlexName}
      </a>
      {EVIDENCE_ATTRIBUTION.openAlexCredit}
    </p>
  );
}

/**
 * The backend counts are authoritative when it has attempted a free-version
 * lookup. This avoids treating every paper in the original fallback list as
 * manual work after a usable version has already been found.
 */
export function getPaywalledFollowUpSummary(
  paywalledMarkdown: string,
  paywalledCount: number,
  enrichment?: EnrichmentData,
): PaywalledFollowUpSummary {
  const resolutionsMarkdown = enrichment?.resolutions_markdown.trim() ?? "";
  const usesEnrichment = Boolean(
    resolutionsMarkdown ||
      (enrichment && (enrichment.resolved_count > 0 || enrichment.unresolved_count > 0)),
  );
  const resolvedCount = usesEnrichment ? (enrichment?.resolved_count ?? 0) : 0;
  const unresolvedCount = usesEnrichment ? (enrichment?.unresolved_count ?? 0) : 0;
  const totalCount = resolvedCount + unresolvedCount;

  if (resolvedCount > 0 && totalCount > 0) {
    const available = `${resolvedCount} of ${totalCount} ${paperLabel(totalCount)} available free`;

    return {
      shouldRender: Boolean(paywalledMarkdown || resolutionsMarkdown),
      usesEnrichment,
      resolvedCount,
      totalCount,
      title: "Paper access follow-up",
      // Deliberately does NOT restate the counts. The badge beside the title
      // and the link in the summary bar both carry "N of M", and the resolution
      // markdown rendered just below opens with its own "N of M paywalled
      // paper(s) have a free version available" line — so repeating the number
      // here made the card say the same thing three times in a row.
      description:
        "Free versions were located automatically where one exists." +
        (unresolvedCount > 0
          ? " The rest need institutional access or library services."
          : ""),
      linkLabel: available,
    };
  }

  if (usesEnrichment && unresolvedCount > 0) {
    const manual = `${unresolvedCount} ${paperLabel(unresolvedCount)} to retrieve manually`;
    return {
      shouldRender: Boolean(paywalledMarkdown || resolutionsMarkdown),
      usesEnrichment,
      resolvedCount,
      totalCount,
      title: "Papers to retrieve manually",
      description: `High-quality and relevant, but not fully accessible. ${manual}.`,
      linkLabel: manual,
    };
  }

  if (usesEnrichment) {
    return {
      shouldRender: Boolean(paywalledMarkdown || resolutionsMarkdown),
      usesEnrichment,
      resolvedCount,
      totalCount,
      title: "Paper access follow-up",
      description: "Free-version check results appear below alongside the original retrieval list.",
      linkLabel: "Paper access follow-up",
    };
  }

  return {
    shouldRender: Boolean(paywalledMarkdown),
    usesEnrichment,
    resolvedCount,
    totalCount,
    title: "Papers to retrieve manually",
    description: "High-quality and relevant, but not fully accessible. Retrieve these through institutional access or library services.",
    linkLabel: paywalledCount > 0
      ? `${paywalledCount} papers to retrieve manually`
      : "Papers to retrieve manually",
  };
}

interface PaywalledFollowUpCardProps {
  paywalledMarkdown: string;
  paywalledCount: number;
  enrichment?: EnrichmentData;
  showAttribution?: boolean;
}

export function PaywalledFollowUpCard({
  paywalledMarkdown,
  paywalledCount,
  enrichment,
  showAttribution = false,
}: PaywalledFollowUpCardProps) {
  const [showPaywalled, setShowPaywalled] = useState(false);
  const summary = getPaywalledFollowUpSummary(paywalledMarkdown, paywalledCount, enrichment);
  const resolutionsMarkdown = enrichment?.resolutions_markdown.trim() ?? "";

  if (!summary.shouldRender) return null;

  return (
    <div
      id="papers-to-retrieve"
      className="scroll-mt-6 rounded-lg border border-[var(--color-info)]/25 bg-[var(--color-info-bg)] p-4"
    >
      <button
        type="button"
        onClick={() => setShowPaywalled((shown) => !shown)}
        aria-expanded={showPaywalled}
        className="flex w-full items-center justify-between gap-3 text-left"
      >
        <span className="min-w-0">
          <span className="text-h3 text-[var(--color-info-text)]">{summary.title}</span>
          {summary.usesEnrichment && summary.totalCount > 0 ? (
            <span className="ml-2 inline-block align-middle">
              <Badge tone="info">
                {summary.resolvedCount > 0
                  ? `${summary.resolvedCount} of ${summary.totalCount} available`
                  : `${summary.totalCount} to retrieve`}
              </Badge>
            </span>
          ) : paywalledCount > 0 ? (
            <span className="ml-2 text-caption text-[var(--color-info-text)]">
              {paywalledCount}
            </span>
          ) : null}
        </span>
        <CaretDownIcon
          size={18}
          className={`shrink-0 text-[var(--color-info-text)] transition-transform duration-150 ${showPaywalled ? "rotate-180" : ""}`}
        />
      </button>
      <p className="mt-1 text-caption text-[var(--color-info-text)]">{summary.description}</p>
      {showPaywalled && (
        <div className="mt-3 min-w-0 break-words text-[var(--color-text-primary)]">
          {resolutionsMarkdown && (
            <div className={paywalledMarkdown ? "border-b border-[var(--color-info)]/25 pb-4" : ""}>
              <Markdown headingIds={false}>{resolutionsMarkdown}</Markdown>
            </div>
          )}
          {paywalledMarkdown && (
            <div className={resolutionsMarkdown ? "pt-4" : ""}>
              <Markdown headingIds={false}>
                {paywalledMarkdown.replace(/^#+ .*\n/, "")}
              </Markdown>
            </div>
          )}
          {showAttribution && <EvidenceAttribution />}
        </div>
      )}
    </div>
  );
}

interface CitationCheckCardProps {
  enrichment?: EnrichmentData;
  showAttribution?: boolean;
}

export function CitationCheckCard({
  enrichment,
  showAttribution = false,
}: CitationCheckCardProps) {
  const [showVerification, setShowVerification] = useState(false);
  const verificationMarkdown = enrichment?.verification_markdown.trim() ?? "";
  const unverifiedDois = enrichment?.unverified_dois ?? [];

  if (!verificationMarkdown && unverifiedDois.length === 0) return null;

  return (
    <div className="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] p-4">
      <button
        type="button"
        onClick={() => setShowVerification((shown) => !shown)}
        aria-expanded={showVerification}
        className="flex w-full items-center justify-between gap-3 text-left"
      >
        <span className="min-w-0">
          <span className="text-h3">Citation check</span>
          {unverifiedDois.length > 0 && (
            <span className="ml-2 inline-block align-middle">
              <Badge tone="neutral">{unverifiedDois.length} to check</Badge>
            </span>
          )}
        </span>
        <CaretDownIcon
          size={18}
          className={`shrink-0 text-[var(--color-text-tertiary)] transition-transform duration-150 ${showVerification ? "rotate-180" : ""}`}
        />
      </button>
      <p className="mt-1 text-caption text-[var(--color-text-secondary)]">
        DOIs that could not be verified in OpenAlex should be checked manually. Coverage gaps can include recent papers, working papers, and DOI formatting variations.
      </p>
      {showVerification && (
        <div className="mt-3 min-w-0 break-words border-t border-[var(--color-border-subtle)] pt-3">
          {verificationMarkdown ? (
            <Markdown headingIds={false}>{verificationMarkdown}</Markdown>
          ) : (
            <ul className="list-inside list-disc text-body text-[var(--color-text-secondary)]">
              {unverifiedDois.map((doi) => (
                <li key={doi} className="break-words">{doi}</li>
              ))}
            </ul>
          )}
          {showAttribution && <EvidenceAttribution />}
        </div>
      )}
    </div>
  );
}
