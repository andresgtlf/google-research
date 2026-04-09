export interface Population {
  description: string
  youth_pct: number | null
  women_pct: number | null
  baseline_income_note: string
}

export interface Scale {
  by_group: Record<string, number>
  time_horizon_years: number | null
}

export interface IntendedOutcomes {
  direct: string[]
  indirect: string[]
  magnitudes: string[]
}

export interface Funding {
  gitlab_request_usd: number | null
  total_project_budget_usd: number | null
}

export interface Extraction {
  organization: string
  project_title: string
  summary: string
  intervention_types: string[]
  mechanisms_to_affect_income: string
  country: string
  region: string
  population: Population
  scale: Scale
  intended_outcomes: IntendedOutcomes
  funding: Funding
  self_reported_evidence: string[]
}

export interface ExtractionResult {
  taskId: string
  extraction: Extraction
  researchPrompt: string
}

export interface ResearchStatus {
  status: "pending" | "running" | "completed" | "failed"
  progress?: string
  interactionId?: string
  result?: string
  error?: string
}

export interface ExportResult {
  markdownUrl?: string
  pdfUrl?: string
  markdownContent?: string
}

export type Step = "upload" | "extract" | "research" | "download"

export interface TaskState {
  taskId: string | null
  step: Step
  extraction: Extraction | null
  researchPrompt: string | null
  researchStatus: ResearchStatus | null
  researchResult: string | null
  exportResult: ExportResult | null
  error: string | null
}
