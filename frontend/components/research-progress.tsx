"use client"

import { useEffect, useState } from "react"
import type { ResearchStatus } from "@/lib/types"
import { formatDuration } from "@/lib/utils"
import { Loader2, Search, CheckCircle2, XCircle } from "lucide-react"

interface ResearchProgressProps {
  status: ResearchStatus
  startTime: number
}

const statusMessages: Record<string, string[]> = {
  pending: ["Initializing research task...", "Preparing analysis parameters..."],
  running: [
    "Searching for relevant studies...",
    "Analyzing RCTs and quasi-experimental data...",
    "Gathering country-specific evidence...",
    "Evaluating methodology quality...",
    "Compiling income effect data...",
    "Cross-referencing baseline surveys...",
    "Assessing external validity...",
    "Building evidence synthesis...",
  ],
}

export function ResearchProgress({ status, startTime }: ResearchProgressProps) {
  const [elapsedTime, setElapsedTime] = useState(0)
  const [messageIndex, setMessageIndex] = useState(0)

  useEffect(() => {
    if (status.status === "completed" || status.status === "failed") return

    const timer = setInterval(() => {
      setElapsedTime(Math.floor((Date.now() - startTime) / 1000))
    }, 1000)

    return () => clearInterval(timer)
  }, [startTime, status.status])

  useEffect(() => {
    if (status.status === "completed" || status.status === "failed") return

    const messages = statusMessages[status.status] || statusMessages.running
    const interval = setInterval(() => {
      setMessageIndex((prev) => (prev + 1) % messages.length)
    }, 8000)

    return () => clearInterval(interval)
  }, [status.status])

  const messages = statusMessages[status.status] || statusMessages.running
  const currentMessage = status.progress || messages[messageIndex]

  return (
    <div className="w-full max-w-2xl mx-auto">
      <div className="flex flex-col items-center gap-6 p-8 rounded-xl border border-border bg-card">
        {status.status === "completed" ? (
          <CheckCircle2 className="h-16 w-16 text-success" />
        ) : status.status === "failed" ? (
          <XCircle className="h-16 w-16 text-destructive" />
        ) : (
          <div className="relative">
            <Search className="h-16 w-16 text-primary" />
            <Loader2 className="h-8 w-8 text-primary animate-spin absolute -bottom-1 -right-1 bg-card rounded-full p-1" />
          </div>
        )}

        <div className="text-center space-y-2">
          <h3 className="text-xl font-semibold">
            {status.status === "completed"
              ? "Research Complete"
              : status.status === "failed"
              ? "Research Failed"
              : "Deep Research in Progress"}
          </h3>
          <p className="text-muted-foreground">{currentMessage}</p>
        </div>

        {status.status !== "completed" && status.status !== "failed" && (
          <>
            <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
              <div className="h-full bg-primary rounded-full animate-pulse w-full opacity-50" />
            </div>

            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span>Elapsed time:</span>
              <span className="font-mono">{formatDuration(elapsedTime)}</span>
            </div>

            <p className="text-xs text-muted-foreground text-center max-w-md">
              Deep research typically takes 5-15 minutes. The AI is searching
              academic databases, analyzing studies, and synthesizing evidence.
            </p>
          </>
        )}

        {status.status === "failed" && status.error && (
          <div className="w-full p-4 bg-destructive/10 border border-destructive/30 rounded-lg">
            <p className="text-sm text-destructive">{status.error}</p>
          </div>
        )}
      </div>
    </div>
  )
}
