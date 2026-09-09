import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJob, fetchProviders, startExtraction, startResearch } from "../api";
import type { AppPhase, Job, ProviderInfo, ResearchMode } from "../types";
import { clearPersistedState, loadPersistedState, savePersistedState } from "./persist";
import { useJobPoller } from "./useJobPoller";

function describeJobFailure(job: Job): string {
  if (job.status === "interrupted") {
    return (
      job.error ||
      "The server restarted while this job was running. It cannot be resumed. Start again."
    );
  }
  return job.error || "The job did not complete. Retry, or edit the prompt first.";
}

function placeholderJob(id: string, kind: "extract" | "research", provider: string | null): Job {
  const now = new Date().toISOString();
  return {
    id,
    kind,
    status: "queued",
    created_at: now,
    updated_at: now,
    events: [],
    error: null,
    provider,
    model: null,
    result: {},
  };
}

/**
 * All wizard state and its lifecycle: persistence to localStorage, rehydration
 * on mount (re-fetching whatever job was in flight and resuming polling),
 * tolerant polling via useJobPoller, and the extract-then-research
 * sequencing. Pulled out of App.tsx so the component tree stays small and
 * focused on layout.
 */
export function useAppSession() {
  const [hydrated, setHydrated] = useState(false);
  const [hydrationNotice, setHydrationNotice] = useState<string | null>(null);

  const [phase, setPhase] = useState<AppPhase>("configure");
  const [file, setFile] = useState<File | null>(null);
  const [freshSearch, setFreshSearch] = useState(false);
  const [mode, setMode] = useState<ResearchMode>("standard");
  const [providerId, setProviderId] = useState("gemini");
  const [tier, setTier] = useState("max");

  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [providersError, setProvidersError] = useState<string | null>(null);

  const [extractJob, setExtractJob] = useState<Job | null>(null);
  const [researchJob, setResearchJob] = useState<Job | null>(null);
  const [researchPrompt, setResearchPrompt] = useState("");
  const [extractError, setExtractError] = useState<string | null>(null);
  const [fatalError, setFatalError] = useState<string | null>(null);

  // Guards against launching the research job twice for the same
  // extraction when a resumed poller and the rehydration path both race to
  // auto-continue "standard" mode after extraction completes.
  const researchLaunchedRef = useRef<string | null>(null);

  const loadProviders = useCallback(() => {
    setProvidersError(null);
    fetchProviders()
      .then(setProviders)
      .catch((e: unknown) => {
        setProvidersError(e instanceof Error ? e.message : "Could not load research engines");
      });
  }, []);

  useEffect(() => {
    loadProviders();
  }, [loadProviders]);

  const launchResearch = useCallback(
    async (
      extractJobId: string,
      prompt: string | undefined,
      overrideProvider?: string,
      overrideTier?: string,
      overrideFresh?: boolean
    ) => {
      const useProvider = overrideProvider ?? providerId;
      const useTier = overrideTier ?? tier;
      try {
        const jobId = await startResearch({
          extract_job_id: extractJobId,
          research_prompt: prompt,
          provider: useProvider,
          tier: useTier,
          formats: ["markdown", "pdf"],
          reuse_existing: !(overrideFresh ?? freshSearch),
        });
        setResearchJob(placeholderJob(jobId, "research", useProvider));
        setPhase("researching");
      } catch (e) {
        setFatalError(e instanceof Error ? e.message : "Could not start the research job");
        setPhase("error");
      }
    },
    [providerId, tier, freshSearch]
  );

  const beginResearchOnce = useCallback(
    (extractJobId: string, prompt: string, overrideProvider?: string, overrideTier?: string, overrideFresh?: boolean) => {
      if (researchLaunchedRef.current === extractJobId) return;
      researchLaunchedRef.current = extractJobId;
      void launchResearch(extractJobId, prompt, overrideProvider, overrideTier, overrideFresh);
    },
    [launchResearch]
  );

  // ── Rehydrate from localStorage on mount ─────────────────────────
  useEffect(() => {
    let cancelled = false;

    async function rehydrate() {
      const persisted = loadPersistedState();
      if (!persisted) {
        setHydrated(true);
        return;
      }
      setMode(persisted.mode ?? "standard");
      setProviderId(persisted.providerId ?? "gemini");
      setTier(persisted.tier ?? (persisted.providerId === "gemini" || !persisted.providerId ? "max" : "fast"));

      try {
        if (persisted.researchJobId) {
          const job = await fetchJob(persisted.researchJobId);
          if (cancelled) return;
          setResearchJob(job);
          if (job.status === "completed") setPhase("complete");
          else if (job.status === "failed" || job.status === "interrupted") {
            setFatalError(describeJobFailure(job));
            setPhase("error");
          } else {
            setPhase("researching");
          }
        } else if (persisted.extractJobId) {
          const job = await fetchJob(persisted.extractJobId);
          if (cancelled) return;
          setExtractJob(job);
          if (job.status === "completed") {
            const prompt = job.result.research_prompt ?? "";
            setResearchPrompt(prompt);
            if (persisted.mode === "customized") {
              setPhase("review");
            } else {
              setPhase("extracting");
              beginResearchOnce(job.id, prompt, persisted.providerId, persisted.tier, persisted.freshSearch ?? false);
            }
          } else if (job.status === "failed" || job.status === "interrupted") {
            setExtractError(describeJobFailure(job));
            setPhase("configure");
          } else {
            setPhase("extracting");
          }
        }
      } catch {
        if (cancelled) return;
        clearPersistedState();
        setHydrationNotice("Your previous session could not be found. Start a new analysis.");
        setPhase("configure");
      } finally {
        if (!cancelled) setHydrated(true);
      }
    }

    void rehydrate();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Persist wizard state on every relevant change ────────────────
  useEffect(() => {
    if (!hydrated) return;
    savePersistedState({
      freshSearch,
      phase,
      extractJobId: extractJob?.id ?? null,
      researchJobId: researchJob?.id ?? null,
      mode,
      providerId,
      tier,
    });
  }, [hydrated, phase, extractJob?.id, researchJob?.id, mode, providerId, tier, freshSearch]);

  // ── Poll extraction job ───────────────────────────────────────────
  useJobPoller({
    jobId: extractJob?.id ?? null,
    active: phase === "extracting",
    onUpdate: setExtractJob,
    onTerminal: (job) => {
      if (job.status === "completed") {
        const prompt = job.result.research_prompt ?? "";
        setResearchPrompt(prompt);
        if (mode === "customized") setPhase("review");
        else beginResearchOnce(job.id, prompt);
      } else {
        setExtractError(describeJobFailure(job));
        setExtractJob(null);
        setPhase("configure");
      }
    },
    onFatalError: (message) => {
      setExtractError(message);
      setExtractJob(null);
      setPhase("configure");
    },
  });

  // ── Poll research job ─────────────────────────────────────────────
  useJobPoller({
    jobId: researchJob?.id ?? null,
    active: phase === "researching",
    onUpdate: setResearchJob,
    onTerminal: (job) => {
      if (job.status === "completed") setPhase("complete");
      else {
        setFatalError(describeJobFailure(job));
        setPhase("error");
      }
    },
    onFatalError: (message) => {
      setFatalError(message);
      setPhase("error");
    },
  });

  const handleStart = useCallback(async () => {
    if (!file) return;
    setExtractError(null);
    setHydrationNotice(null);
    try {
      const jobId = await startExtraction(file, freshSearch);
      setExtractJob(placeholderJob(jobId, "extract", null));
      setPhase("extracting");
    } catch (e) {
      setExtractError(e instanceof Error ? e.message : "Could not start extraction");
    }
  }, [file, freshSearch]);

  const handleFullReset = useCallback(() => {
    clearPersistedState();
    researchLaunchedRef.current = null;
    setPhase("configure");
    setFile(null);
    setExtractJob(null);
    setResearchJob(null);
    setExtractError(null);
    setFatalError(null);
    setResearchPrompt("");
    setHydrationNotice(null);
  }, []);

  return {
    freshSearch,
    setFreshSearch,
    openSavedReport: (job: Job) => { setResearchJob(job); setPhase("complete"); },
    hydrated,
    hydrationNotice,
    phase,
    file,
    setFile,
    mode,
    setMode,
    providerId,
    setProviderId,
    tier,
    setTier,
    providers,
    providersError,
    loadProviders,
    extractJob,
    researchJob,
    researchPrompt,
    setResearchPrompt,
    extractError,
    setExtractError,
    fatalError,
    setPhase,
    launchResearch,
    handleStart,
    handleFullReset,
  };
}
