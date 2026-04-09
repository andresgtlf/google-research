"use client"

import { useState } from "react"
import type { Extraction } from "@/lib/types"
import { cn } from "@/lib/utils"
import {
  Building2,
  MapPin,
  Users,
  Target,
  DollarSign,
  FileText,
  ChevronDown,
  Loader2,
} from "lucide-react"

interface ExtractionPreviewProps {
  extraction: Extraction
  researchPrompt: string
  onStartResearch: () => Promise<void>
  isLoading: boolean
}

interface SectionProps {
  title: string
  icon: React.ReactNode
  children: React.ReactNode
  defaultOpen?: boolean
}

function Section({ title, icon, children, defaultOpen = true }: SectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between gap-3 p-4 bg-muted/50 hover:bg-muted transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-primary">{icon}</span>
          <span className="font-medium">{title}</span>
        </div>
        <ChevronDown
          className={cn(
            "h-5 w-5 text-muted-foreground transition-transform",
            isOpen && "rotate-180"
          )}
        />
      </button>
      {isOpen && <div className="p-4 space-y-3">{children}</div>}
    </div>
  )
}

function DataRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (!value || (Array.isArray(value) && value.length === 0)) return null
  return (
    <div className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-4">
      <span className="text-sm text-muted-foreground min-w-[140px]">{label}</span>
      <span className="text-sm">{value}</span>
    </div>
  )
}

export function ExtractionPreview({
  extraction,
  researchPrompt,
  onStartResearch,
  isLoading,
}: ExtractionPreviewProps) {
  return (
    <div className="w-full max-w-3xl mx-auto space-y-6">
      <div className="text-center space-y-2">
        <h2 className="text-2xl font-semibold">{extraction.project_title}</h2>
        <p className="text-muted-foreground">{extraction.organization}</p>
      </div>

      <div className="space-y-4">
        <Section
          title="Organization & Project"
          icon={<Building2 className="h-5 w-5" />}
        >
          <DataRow label="Summary" value={extraction.summary} />
          <DataRow
            label="Intervention Types"
            value={extraction.intervention_types?.join(", ")}
          />
          <DataRow
            label="Mechanisms"
            value={extraction.mechanisms_to_affect_income}
          />
        </Section>

        <Section
          title="Geography & Population"
          icon={<MapPin className="h-5 w-5" />}
        >
          <DataRow
            label="Location"
            value={
              extraction.region
                ? `${extraction.country}, ${extraction.region}`
                : extraction.country
            }
          />
          <DataRow
            label="Target Population"
            value={extraction.population?.description}
          />
          {extraction.population?.youth_pct && (
            <DataRow
              label="Youth %"
              value={`${extraction.population.youth_pct}%`}
            />
          )}
          {extraction.population?.women_pct && (
            <DataRow
              label="Women %"
              value={`${extraction.population.women_pct}%`}
            />
          )}
          <DataRow
            label="Baseline Income"
            value={extraction.population?.baseline_income_note}
          />
        </Section>

        <Section title="Scale" icon={<Users className="h-5 w-5" />}>
          {extraction.scale?.by_group &&
            Object.entries(extraction.scale.by_group).map(([group, count]) => (
              <DataRow key={group} label={group} value={count?.toLocaleString()} />
            ))}
          {extraction.scale?.time_horizon_years && (
            <DataRow
              label="Time Horizon"
              value={`${extraction.scale.time_horizon_years} years`}
            />
          )}
        </Section>

        <Section
          title="Intended Outcomes"
          icon={<Target className="h-5 w-5" />}
          defaultOpen={false}
        >
          {extraction.intended_outcomes?.direct?.length > 0 && (
            <div className="space-y-1">
              <span className="text-sm text-muted-foreground">Direct:</span>
              <ul className="list-disc list-inside text-sm space-y-1 ml-2">
                {extraction.intended_outcomes.direct.map((outcome, i) => (
                  <li key={i}>{outcome}</li>
                ))}
              </ul>
            </div>
          )}
          {extraction.intended_outcomes?.indirect?.length > 0 && (
            <div className="space-y-1">
              <span className="text-sm text-muted-foreground">Indirect:</span>
              <ul className="list-disc list-inside text-sm space-y-1 ml-2">
                {extraction.intended_outcomes.indirect.map((outcome, i) => (
                  <li key={i}>{outcome}</li>
                ))}
              </ul>
            </div>
          )}
          {extraction.intended_outcomes?.magnitudes?.length > 0 && (
            <div className="space-y-1">
              <span className="text-sm text-muted-foreground">Magnitudes:</span>
              <ul className="list-disc list-inside text-sm space-y-1 ml-2">
                {extraction.intended_outcomes.magnitudes.map((mag, i) => (
                  <li key={i}>{mag}</li>
                ))}
              </ul>
            </div>
          )}
        </Section>

        <Section
          title="Funding"
          icon={<DollarSign className="h-5 w-5" />}
          defaultOpen={false}
        >
          {extraction.funding?.gitlab_request_usd && (
            <DataRow
              label="GitLab Request"
              value={`$${extraction.funding.gitlab_request_usd.toLocaleString()}`}
            />
          )}
          {extraction.funding?.total_project_budget_usd && (
            <DataRow
              label="Total Budget"
              value={`$${extraction.funding.total_project_budget_usd.toLocaleString()}`}
            />
          )}
        </Section>

        {extraction.self_reported_evidence?.length > 0 && (
          <Section
            title="Self-Reported Evidence"
            icon={<FileText className="h-5 w-5" />}
            defaultOpen={false}
          >
            <ul className="list-disc list-inside text-sm space-y-2 ml-2">
              {extraction.self_reported_evidence.map((evidence, i) => (
                <li key={i}>{evidence}</li>
              ))}
            </ul>
          </Section>
        )}
      </div>

      <div className="pt-4 flex flex-col items-center gap-4">
        <p className="text-sm text-muted-foreground text-center max-w-lg">
          Ready to search for external evidence? This will use deep research to
          find relevant studies and data supporting the impact claims.
        </p>
        <button
          type="button"
          onClick={onStartResearch}
          disabled={isLoading}
          className="px-8 py-3 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 transition-colors disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {isLoading ? (
            <>
              <Loader2 className="h-5 w-5 animate-spin" />
              Starting Research...
            </>
          ) : (
            "Start Deep Research"
          )}
        </button>
      </div>
    </div>
  )
}
