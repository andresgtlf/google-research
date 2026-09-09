import type { AppPhase } from "./types";
import { useAppSession } from "./lib/useAppSession";
import Header from "./components/Header";
import Stepper, { STEP_LABELS } from "./components/Stepper";
import ConfigureStep from "./components/ConfigureStep";
import PromptReview from "./components/PromptReview";
import ProgressView from "./components/ProgressView";
import EvidenceSourceStatus from "./components/EvidenceSourceStatus";
import ResearchLibrary from "./components/ResearchLibrary";
import Results from "./components/Results";
import ResearchErrorCard from "./components/ResearchErrorCard";
import ErrorBoundary from "./components/ErrorBoundary";

// Extraction runs BEFORE the review step, so it stays on Upload. Mapping it
// to Progress marked Review as already done while the reviewer had not yet
// seen the prompt.
function stepIndexForPhase(phase: AppPhase): number {
  switch (phase) {
    case "configure":
    case "extracting":
      return 0;
    case "review":
      return 1;
    case "researching":
    case "error":
      return 2;
    case "complete":
      return 3;
  }
}

const STEP_MAX_WIDTH: Record<string, string> = {
  configure: "max-w-2xl",
  review: "max-w-4xl",
  extracting: "max-w-3xl",
  researching: "max-w-3xl",
  error: "max-w-2xl",
};

/**
 * Shell + routing only. The wizard's state machine lives in
 * useAppSession (persistence, rehydration, tolerant polling, the
 * extract-then-research sequencing); the four steps are each their own
 * component. Header and Stepper sit outside the per-step content slot and
 * never change width or position across steps (spec Section 5).
 */
export default function App() {
  const session = useAppSession();

  const provider = session.providers.find((p) => p.id === session.providerId);
  const stepIndex = stepIndexForPhase(session.phase);
  const activeJobStatus =
    session.phase === "extracting"
      ? session.extractJob?.status
      : session.phase === "researching" || session.phase === "complete" || session.phase === "error"
        ? session.researchJob?.status
        : undefined;

  if (!session.hydrated) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-[var(--color-surface-0)]">
        <p className="text-body text-[var(--color-text-secondary)]">Loading…</p>
      </div>
    );
  }

  const startDisabledReason = session.providersError
    ? "Research engines unavailable"
    : !session.file
      ? "Upload a PDF or Word document to start"
      : provider && !provider.available
        ? `${provider.label} needs an API key`
        : null;

  return (
    <div className="min-h-dvh bg-[var(--color-surface-0)]">
      <Header
        stepLabel={STEP_LABELS[stepIndex]}
        stepIndex={stepIndex}
        totalSteps={STEP_LABELS.length}
        jobStatus={activeJobStatus}
        showReset={session.phase !== "configure"}
        onReset={session.handleFullReset}
      />
      <Stepper currentIndex={stepIndex} />

      <main className="mx-auto max-w-[1200px] px-6 py-10">
        <div key={session.phase} className="step-enter">
          {session.phase === "complete" && session.researchJob ? (
            <ErrorBoundary area="the results view" onReset={session.handleFullReset}>
              <Results job={session.researchJob} />
            </ErrorBoundary>
          ) : (
            <div className={`mx-auto ${STEP_MAX_WIDTH[session.phase] ?? "max-w-2xl"}`}>
              {session.phase === "configure" && (
                <>
                <ConfigureStep
                  documentFormat={session.documentFormat}
                  onDocumentFormat={session.setDocumentFormat}
                  file={session.file}
                  onFile={session.setFile}
                  mode={session.mode}
                  onMode={session.setMode}
                  providerId={session.providerId}
                  tier={session.tier}
                  onProviderSelect={session.setProviderId}
                  onTier={session.setTier}
                  providers={session.providers}
                  providersError={session.providersError}
                  onRetryProviders={session.loadProviders}
                  extractError={session.extractError}
                  onDismissExtractError={() => session.setExtractError(null)}
                  hydrationNotice={session.hydrationNotice}
                  onStart={session.handleStart}
                  startDisabledReason={startDisabledReason}
                />
                <label className="mt-5 flex items-start gap-3 text-caption">
                  <input type="checkbox" checked={session.freshSearch} onChange={(e) => session.setFreshSearch(e.target.checked)} className="mt-1" />
                  <span>Run a fresh search. Otherwise reuse the saved extraction, evidence and matching report when available. Fresh searches use API credits and may find different papers.</span>
                </label>
                <ResearchLibrary onOpen={session.openSavedReport} />
                </>
              )}

              {(session.phase === "extracting" || session.phase === "researching") && (
                <ProgressView
                  phase={session.phase}
                  job={session.phase === "extracting" ? session.extractJob : session.researchJob}
                  providerLabel={provider?.label ?? session.providerId}
                />
              )}

              {session.phase === "review" && (
                <div className="space-y-6">
                <EvidenceSourceStatus status={session.extractJob?.evidence_status} terminal />
                <PromptReview
                  extraction={session.extractJob?.result?.extraction}
                  prompt={session.researchPrompt}
                  onPromptChange={session.setResearchPrompt}
                  onRun={() =>
                    session.extractJob &&
                    session.launchResearch(session.extractJob.id, session.researchPrompt)
                  }
                  onReset={session.handleFullReset}
                />
                </div>
              )}

              {session.phase === "error" && (
                <ResearchErrorCard
                  message={session.fatalError}
                  canRetryWithPrompt={Boolean(session.extractJob && session.researchPrompt)}
                  onRetry={() => session.setPhase("review")}
                  onReset={session.handleFullReset}
                />
              )}
            </div>
          )}
        </div>
      </main>

      <footer className="mx-auto max-w-[1200px] border-t border-[var(--color-border-subtle)] px-6 py-4 text-center text-caption text-[var(--color-text-tertiary)]">
        GitLab Foundation Research. Multi-provider deep research (Gemini, OpenAI, Claude).
      </footer>
    </div>
  );
}
