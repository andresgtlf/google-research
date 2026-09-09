import { useEffect, useState } from "react";
import type { ReportHeading } from "../lib/reportHeadings";

/**
 * Sticky left rail (spec Section 5/6) built from the report's own H1/H2
 * headings. Active section tracked with IntersectionObserver, never a
 * scroll listener (spec Section 7 - the one point of agreement across all
 * three design skills this spec drew from). Collapses to a horizontal
 * scrollable chip row below `lg` rather than disappearing, since a long
 * report needs in-page navigation on tablet too.
 */
export default function ResultsSectionNav({ headings }: { headings: ReportHeading[] }) {
  const [activeId, setActiveId] = useState<string | null>(headings[0]?.id ?? null);

  useEffect(() => {
    if (headings.length === 0) return;
    const elements = headings
      .map((h) => document.getElementById(h.id))
      .filter((el): el is HTMLElement => el !== null);
    if (elements.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting);
        if (visible.length === 0) return;
        const topMost = visible.reduce((a, b) =>
          a.boundingClientRect.top < b.boundingClientRect.top ? a : b
        );
        setActiveId(topMost.target.id);
      },
      { rootMargin: "-96px 0px -70% 0px", threshold: 0 }
    );
    elements.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [headings]);

  if (headings.length === 0) return null;

  return (
    <>
      <nav aria-label="Report sections" className="hidden shrink-0 lg:block lg:w-64">
        <div className="sticky top-4 space-y-1">
          {headings.map((h) => (
            <a
              key={h.id}
              href={`#${h.id}`}
              className={`block truncate rounded-lg border-l-2 py-1.5 text-label transition-colors duration-150 ${
                h.level === 2 ? "pl-6" : "pl-3"
              } ${
                activeId === h.id
                  ? "border-[var(--color-accent)] bg-[var(--color-accent-subtle)] text-[var(--color-text-primary)]"
                  : "border-transparent text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-2)]"
              }`}
            >
              {h.text}
            </a>
          ))}
        </div>
      </nav>

      <div className="-mx-6 overflow-x-auto px-6 pb-2 lg:hidden">
        <div className="flex min-w-max gap-2">
          {headings.map((h) => (
            <a
              key={h.id}
              href={`#${h.id}`}
              className={`shrink-0 whitespace-nowrap rounded-full border px-3 py-1 text-caption transition-colors duration-150 ${
                activeId === h.id
                  ? "border-[var(--color-accent)] bg-[var(--color-accent-subtle)] text-[var(--color-text-primary)]"
                  : "border-[var(--color-border-subtle)] text-[var(--color-text-secondary)]"
              }`}
            >
              {h.text}
            </a>
          ))}
        </div>
      </div>
    </>
  );
}
