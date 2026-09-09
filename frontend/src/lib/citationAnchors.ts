/** Recognize only our exact generated anchor markup. No arbitrary HTML is enabled. */
interface Node {
  type: string;
  value?: string;
  children?: Node[];
  data?: { hName?: string; hProperties?: Record<string, unknown> };
}

export function citationAnchors({ emitIds = true }: { emitIds?: boolean } = {}) {
  return (tree: Node) => {
    function visit(node: Node) {
      if (!node.children) return;
      let reference = false;
      let skipClosing = false;
      node.children = node.children.flatMap((child, index, siblings) => {
        if (skipClosing) { skipClosing = false; return []; }
        if (child.type === "html") {
          const match = /^<a id="((?:ref-[a-z0-9-]+|cite-ref-[a-z0-9-]+-\d+|report-start))">(<\/a>)?$/.exec(child.value ?? "");
          if (match && (match[2] || siblings[index + 1]?.value === "</a>")) {
            skipClosing = !match[2];
            reference ||= match[1].startsWith("ref-");
            return emitIds ? [{ type: "citationAnchor", children: [], data: {
              hName: "span", hProperties: { id: match[1], tabIndex: -1, className: "citation-anchor" },
            } }] : [];
          }
        }
        visit(child);
        return [child];
      });
      if (reference && node.type === "paragraph") {
        node.data = { ...node.data, hProperties: { ...node.data?.hProperties, className: "apa-reference" } };
      }
    }
    visit(tree);
  };
}
