export interface ReportHeading {
  level: 1 | 2;
  text: string;
  id: string;
}

/** Shared between the heading list builder below and the <Markdown> H1/H2
 * renderers, so a nav link's href always matches the id actually rendered
 * on the corresponding heading. */
export function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

/**
 * Builds the sticky section-nav list from the report's own H1/H2 lines.
 * A lightweight line scan rather than a second full markdown-AST parse:
 * the report headings always start a line with `#`/`##` in the markdown
 * this app generates, so this is a deliberate simplification over walking
 * remark's AST a second time, kept because it is far less code for the
 * same practical result (see project notes for the tradeoff).
 */
export function extractHeadings(markdown: string): ReportHeading[] {
  const headings: ReportHeading[] = [];
  const seenIds = new Map<string, number>();
  for (const rawLine of markdown.split("\n")) {
    const line = rawLine.trim();
    const match = /^(#{1,2})\s+(.+)$/.exec(line);
    if (!match) continue;
    const level = match[1].length as 1 | 2;
    const text = match[2].replace(/[#*]+$/, "").trim();
    if (!text) continue;
    let id = slugify(text);
    const count = seenIds.get(id) ?? 0;
    seenIds.set(id, count + 1);
    if (count > 0) id = `${id}-${count}`;
    headings.push({ level, text, id });
  }
  return headings;
}
