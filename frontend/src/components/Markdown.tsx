import { useMemo, useRef, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { slugify } from "../lib/reportHeadings";

function nodeText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(nodeText).join("");
  if (node && typeof node === "object" && "props" in node) {
    return nodeText((node as { props?: { children?: ReactNode } }).props?.children);
  }
  return "";
}

/**
 * Shared markdown renderer for every rendered-report surface in the app.
 * Assigns `id` to H1/H2 the same way `extractHeadings` (lib/reportHeadings)
 * derives the sticky-nav's link targets, using the same slug + de-dupe
 * order (top to bottom, first occurrence wins the bare slug) so a nav
 * click always lands on the right heading. Tables are wrapped so the
 * `.report-table-wrapper` CSS (sticky header/first column, horizontal
 * scroll) in index.css applies without the prose max-width clipping them.
 */
interface MarkdownProps {
  children: string;
  /** Emit `id` on H1/H2 so the sticky nav can link to them. Only the full
   * report should do this: the conclusions and paywalled cards render
   * excerpts of that same report, so leaving ids on produced two elements
   * with `id="conclusions"` and the nav link jumped to the excerpt instead
   * of the section. */
  headingIds?: boolean;
}

export default function Markdown({ children, headingIds = true }: MarkdownProps) {
  // Reset the de-dupe counter whenever the underlying markdown changes so
  // ids stay stable and match extractHeadings for that document.
  const seenIds = useRef(new Map<string, number>());
  const idsForThisRender = useMemo(() => {
    seenIds.current = new Map<string, number>();
    return seenIds.current;
  }, [children]);

  function idFor(text: string): string | undefined {
    if (!headingIds) return undefined;
    const base = slugify(text);
    const count = idsForThisRender.get(base) ?? 0;
    idsForThisRender.set(base, count + 1);
    return count > 0 ? `${base}-${count}` : base;
  }

  return (
    <div className="report-md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children: kids, ...props }) => (
            <h1 id={idFor(nodeText(kids))} {...props}>
              {kids}
            </h1>
          ),
          h2: ({ children: kids, ...props }) => (
            <h2 id={idFor(nodeText(kids))} {...props}>
              {kids}
            </h2>
          ),
          table: ({ children: kids, ...props }) => (
            <div className="report-table-wrapper">
              <table {...props}>{kids}</table>
            </div>
          ),
          a: ({ children: kids, href, ...props }) => (
            <a href={href} target="_blank" rel="noreferrer" {...props}>
              {kids}
            </a>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
