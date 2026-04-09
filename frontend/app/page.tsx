"use client"

import { useState, useEffect, useCallback } from "react"
import { StepIndicator } from "@/components/step-indicator"
import { UploadZone } from "@/components/upload-zone"
import { ExtractionPreview } from "@/components/extraction-preview"
import { ResearchProgress } from "@/components/research-progress"
import { DownloadSection } from "@/components/download-section"
import type {
  Step,
  Extraction,
  ResearchStatus,
  ExportResult,
} from "@/lib/types"

const STORAGE_KEY = "impact-research-state"

interface StoredState {
  taskId: string | null
  step: Step
  extraction: Extraction | null
  researchPrompt: string | null
  researchStartTime: number | null
  researchResult: string | null
}

export default function HomePage() {
  const [step, setStep] = useState<Step>("upload")
  const [taskId, setTaskId] = useState<string | null>(null)
  const [extraction, setExtraction] = useState<Extraction | null>(null)
  const [researchPrompt, setResearchPrompt] = useState<string | null>(null)
  const [researchStatus, setResearchStatus] = useState<ResearchStatus | null>(null)
  const [researchStartTime, setResearchStartTime] = useState<number | null>(null)
  const [researchResult, setResearchResult] = useState<string | null>(null)
  const [exportResult, setExportResult] = useState<ExportResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isExporting, setIsExporting] = useState(false)

  // Load state from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        const state: StoredState = JSON.parse(stored)
        if (state.taskId) {
          setTaskId(state.taskId)
          setStep(state.step)
          setExtraction(state.extraction)
          setResearchPrompt(state.researchPrompt)
          setResearchStartTime(state.researchStartTime)
          setResearchResult(state.researchResult)

          // If research was in progress, resume polling
          if (state.step === "research" && !state.researchResult) {
            setResearchStatus({ status: "running" })
          }
        }
      }
    } catch {
      // Ignore storage errors
    }
  }, [])

  // Save state to localStorage
  useEffect(() => {
    if (taskId) {
      const state: StoredState = {
        taskId,
        step,
        extraction,
        researchPrompt,
        researchStartTime,
        researchResult,
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
    }
  }, [taskId, step, extraction, researchPrompt, researchStartTime, researchResult])

  // Poll for research status
  const pollStatus = useCallback(async () => {
    if (!taskId || step !== "research" || researchResult) return

    try {
      const response = await fetch(`/api/status/${taskId}`)
      if (!response.ok) throw new Error("Failed to fetch status")

      const status: ResearchStatus = await response.json()
      setResearchStatus(status)

      if (status.status === "completed" && status.result) {
        setResearchResult(status.result)
        setStep("download")
      } else if (status.status === "failed") {
        setError(status.error || "Research failed")
      }
    } catch (err) {
      console.error("Status poll error:", err)
      // Don't set error for transient failures, just retry
    }
  }, [taskId, step, researchResult])

  useEffect(() => {
    if (step !== "research" || researchResult) return

    // Initial poll
    pollStatus()

    // Poll every 10 seconds
    const interval = setInterval(pollStatus, 10000)
    return () => clearInterval(interval)
  }, [step, researchResult, pollStatus])

  const handleUpload = async (file: File) => {
    setIsLoading(true)
    setError(null)

    try {
      const formData = new FormData()
      formData.append("file", file)

      const response = await fetch("/api/extract", {
        method: "POST",
        body: formData,
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.error || "Extraction failed")
      }

      const data = await response.json()
      setTaskId(data.taskId)
      setExtraction(data.extraction)
      setResearchPrompt(data.researchPrompt)
      setStep("extract")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed")
    } finally {
      setIsLoading(false)
    }
  }

  const handleStartResearch = async () => {
    if (!taskId || !researchPrompt) return

    setIsLoading(true)
    setError(null)

    try {
      const response = await fetch("/api/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ taskId, researchPrompt }),
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.error || "Failed to start research")
      }

      setResearchStatus({ status: "pending" })
      setResearchStartTime(Date.now())
      setStep("research")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start research")
    } finally {
      setIsLoading(false)
    }
  }

  const handleExport = async (format: "markdown" | "pdf" | "both") => {
    if (!taskId || !researchResult || !extraction) return

    setIsExporting(true)
    setError(null)

    try {
      const response = await fetch("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          taskId,
          format,
          extraction,
          researchResult,
        }),
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.error || "Export failed")
      }

      const data: ExportResult = await response.json()
      setExportResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed")
    } finally {
      setIsExporting(false)
    }
  }

  const handleStartNew = () => {
    setStep("upload")
    setTaskId(null)
    setExtraction(null)
    setResearchPrompt(null)
    setResearchStatus(null)
    setResearchStartTime(null)
    setResearchResult(null)
    setExportResult(null)
    setError(null)
    localStorage.removeItem(STORAGE_KEY)
  }

  return (
    <main className="min-h-screen flex flex-col">
      <header className="border-b border-border bg-card/50 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">Impact Evidence Research</h1>
            <p className="text-sm text-muted-foreground">
              GitLab Foundation
            </p>
          </div>
        </div>
      </header>

      <div className="flex-1 px-4 py-8">
        <div className="max-w-6xl mx-auto space-y-8">
          <StepIndicator currentStep={step} />

          {error && (
            <div className="max-w-2xl mx-auto p-4 bg-destructive/10 border border-destructive/30 rounded-lg">
              <p className="text-sm text-destructive text-center">{error}</p>
            </div>
          )}

          <div className="py-8">
            {step === "upload" && (
              <UploadZone onUpload={handleUpload} isLoading={isLoading} />
            )}

            {step === "extract" && extraction && researchPrompt && (
              <ExtractionPreview
                extraction={extraction}
                researchPrompt={researchPrompt}
                onStartResearch={handleStartResearch}
                isLoading={isLoading}
              />
            )}

            {step === "research" && researchStatus && researchStartTime && (
              <ResearchProgress
                status={researchStatus}
                startTime={researchStartTime}
              />
            )}

            {step === "download" && extraction && researchResult && (
              <DownloadSection
                extraction={extraction}
                researchResult={researchResult}
                exportResult={exportResult}
                onExport={handleExport}
                onStartNew={handleStartNew}
                isExporting={isExporting}
              />
            )}
          </div>
        </div>
      </div>

      <footer className="border-t border-border py-4">
        <div className="max-w-6xl mx-auto px-4 text-center text-sm text-muted-foreground">
          Powered by Gemini AI Deep Research
        </div>
      </footer>
    </main>
  )
}
