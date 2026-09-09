import { useEffect, useRef, type ReactNode } from "react";
import { Badge } from "./Badge";

const LINK_KEYS = ["link", "url"];
const ACCESS_KEYS = ["access"];

type AccessTone = "success" | "info" | "warning" | "danger" | "neutral";

function accessTone(value: string): AccessTone {
  const lower = value.toLowerCase();
  if (lower.includes("open access")) return "success";
  if (lower.includes("working paper")) return "info";
  if (lower.includes("abstract-only") || lower.includes("abstract only")) return "warning";
  if (lower.includes("paywalled")) return "danger";
  return "neutral";
}

/** Safe hostname extraction for a link cell. The previous implementation
 * called `new URL(url)` with no guard, which throws on any malformed link
 * text the research model happened to emit (a stray citation marker,
 * truncated URL, etc.) - and with no error boundary anywhere in the app,
 * that exception blanked the entire results page right after a 20-minute
 * job. This falls back to the raw cell text instead of throwing. */
function renderLinkCell(value: string): ReactNode {
  const match = value.match(/https?:\/\/[^\s)]+/);
  if (!match) return value;
  const url = match[0];
  try {
    const hostname = new URL(url).hostname.replace(/^www\./, "");
    return (
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        className="text-[var(--color-accent-hover)] underline underline-offset-2"
      >
        {hostname}
      </a>
    );
  } catch {
    return value;
  }
}

function updateScrollFade(el: HTMLDivElement) {
  const canScrollRight = el.scrollLeft + el.clientWidth < el.scrollWidth - 2;
  el.style.setProperty("--scroll-fade-opacity", canScrollRight ? "1" : "0");
}

/**
 * The ~8-column evidence digest. First column pinned via `sticky left-0`
 * so the study/source identifier stays visible while the rest scrolls
 * (spec Section 5) - never shrinks font or wraps every cell to force-fit
 * columns. A JS-driven edge fade (not a static decoration) signals there
 * is more to scroll.
 */
export default function ResultsEvidenceTable({ rows }: { rows: Record<string, string>[] }) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    updateScrollFade(el);
  }, [rows]);

  if (rows.length === 0) {
    return (
      <p className="text-body text-[var(--color-text-secondary)]">
        No structured evidence entries were returned for this query.
      </p>
    );
  }

  const columns = Object.keys(rows[0]);

  return (
    <div
      ref={scrollRef}
      onScroll={(e) => updateScrollFade(e.currentTarget)}
      className="scroll-fade-right overflow-x-auto rounded-lg border border-[var(--color-border-subtle)]"
    >
      <table className="w-max min-w-full border-collapse text-mono-data">
        <thead>
          <tr>
            {columns.map((col, i) => (
              <th
                key={col}
                className={`sticky top-0 whitespace-nowrap border-b border-[var(--color-border-subtle)] px-3 py-2 text-left font-sans font-semibold text-[var(--color-text-secondary)] ${
                  i === 0
                    ? "left-0 z-20 bg-[var(--color-surface-1)]"
                    : "z-10 bg-[var(--color-surface-2)]"
                }`}
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map((key, colIndex) => {
                const value = row[key] ?? "";
                const lowerKey = key.toLowerCase();
                let content: ReactNode = value;
                if (LINK_KEYS.some((lk) => lowerKey.includes(lk)) && /https?:\/\//.test(value)) {
                  content = renderLinkCell(value);
                } else if (ACCESS_KEYS.some((ak) => lowerKey.includes(ak)) && value) {
                  content = <Badge tone={accessTone(value)}>{value}</Badge>;
                }
                return (
                  <td
                    key={key}
                    className={`whitespace-nowrap border-b border-[var(--color-border-subtle)] px-3 py-2 align-top ${
                      colIndex === 0
                        ? "sticky left-0 z-10 border-r border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]"
                        : rowIndex % 2 === 1
                          ? "bg-[var(--color-surface-0)]"
                          : ""
                    }`}
                  >
                    {content}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
