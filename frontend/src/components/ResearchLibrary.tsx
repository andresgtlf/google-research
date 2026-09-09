import { useEffect, useState } from "react";
import { fetchJob, fetchLibrary, type LibraryRun } from "../api";
import type { Job } from "../types";
import Button from "./Button";

export default function ResearchLibrary({ onOpen }: { onOpen: (job: Job) => void }) {
  const [query, setQuery] = useState("");
  const [runs, setRuns] = useState<LibraryRun[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const timer = setTimeout(() => {
      fetchLibrary(query).then((rows) => {
        if (!cancelled) { setRuns(rows); setError(""); }
      }).catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load library");
      }).finally(() => { if (!cancelled) setLoading(false); });
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query]);

  async function open(id: string) {
    try { onOpen(await fetchJob(id)); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not open report"); }
  }
  return (
    <section className="mt-8 rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] p-6" aria-label="Research library">
      <h2 className="text-h3">Research library</h2>
      <p className="mt-1 text-caption text-[var(--color-text-secondary)]">Reopen saved reports without running another paid search.</p>
      <label className="mt-4 block text-caption" htmlFor="library-search">Search organization, project, country or engine</label>
      <input id="library-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} className="mt-2 w-full rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-0)] p-3" />
      <div aria-live="polite">
        {error && <p role="alert" className="mt-3 text-caption">{error}</p>}
        {loading ? <p className="mt-4 text-caption">Loading saved research…</p> : !runs.length ? <p className="mt-4 text-caption">{query ? "No matching reports." : "Completed research will appear here."}</p> : (
          <ul className="mt-4 divide-y divide-[var(--color-border-subtle)]">
            {runs.map((run) => <li key={run.id} className="flex flex-wrap items-center justify-between gap-3 py-4">
              <div className="min-w-0 flex-1"><h3 className="font-medium">{run.organization || "Research report"}</h3><p className="text-caption">{run.project_title}</p><p className="mt-1 text-caption text-[var(--color-text-secondary)]">{[run.country, run.provider, new Date(run.created_at).toLocaleDateString()].filter(Boolean).join(" · ")}</p></div>
              <Button variant="secondary" onClick={() => void open(run.id)}>Open report</Button>
            </li>)}
          </ul>
        )}
        {runs.length === 50 && <p className="text-caption">Showing the latest 50 matches. Narrow your search to find older research.</p>}
      </div>
    </section>
  );
}
