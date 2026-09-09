export interface ModelOption {
  id: string;
  label: string;
  tier: "fast" | "max" | "legacy";
  note: string;
}

export interface ProviderInfo {
  id: string;
  label: string;
  description: string;
  env_key: string;
  available: boolean;
  models: ModelOption[];
  recommended_tier: string;
}

export interface JobEvent {
  time: string;
  message: string;
}

export interface ExtractionData {
  organization: string;
  project_title: string;
  summary: string;
  intervention_types: string[];
  country: string;
  region: string;
  population: { description: string };
  funding: {
    gitlab_request_usd: number | null;
    total_project_budget_usd: number | null;
  };
  primary_research_question: string;
}

export interface EnrichmentData {
  resolutions_markdown: string;
  verification_markdown: string;
  resolved_count: number;
  unresolved_count: number;
  /** DOIs OpenAlex could not resolve. These need manual checking, but are
   * not on their own a conclusion about the underlying citation. */
  unverified_dois: string[];
  /** Non-fatal notes from an enrichment step that could not be completed. */
  enrichment_notes: string[];
}

export interface ReportSections {
  evidence_table: Record<string, string>[] | null;
  conclusions: string;
  paywalled: string;
  enrichment?: EnrichmentData;
  /** Non-empty when the backend could not automatically parse one or more
   * sections out of the raw report markdown. Surfaced as a quiet inline
   * notice, and forces the full report view to default to expanded. */
  parse_warnings?: string[];
}

export type JobStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  /** The server restarted while this job was running. Unrecoverable: the
   * job must be re-run, it never resumes on its own. */
  | "interrupted";

export interface EvidenceStatus {
  activity?: string;
  state: "waiting" | "searching" | "complete" | "partial" | "unavailable" | "disabled";
  message: string;
  reused?: boolean;
  queries_completed?: number;
  queries_failed?: number;
  matches?: number;
  retrieved_at?: string;
}

export interface Job {
  evidence_status?: EvidenceStatus;
  id: string;
  kind: "extract" | "research";
  status: JobStatus;
  created_at: string;
  updated_at: string;
  events: JobEvent[];
  error: string | null;
  provider: string | null;
  model: string | null;
  remote_id?: string | null;
  result: {
    extraction?: ExtractionData;
    research_prompt?: string;
    report_markdown?: string;
    run_fingerprint?: string;
    protocol_version?: string;
    sections?: ReportSections;
    files?: Record<string, string>;
  };
}

export type AppPhase =
  | "configure"
  | "extracting"
  | "review"
  | "researching"
  | "complete"
  | "error";

export type ResearchMode = "standard" | "customized";

/** Shape persisted to localStorage so a refresh (or a crash) does not
 * abandon a job that is still alive server-side. Kept intentionally small
 * and serializable. */
export interface PersistedAppState {
  freshSearch?: boolean;
  phase: AppPhase;
  extractJobId: string | null;
  researchJobId: string | null;
  mode: ResearchMode;
  providerId: string;
  tier: string;
}
