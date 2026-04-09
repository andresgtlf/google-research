"use client"

import { useState } from "react"
import ReactMarkdown from "react-markdown"
import type { ExportResult, Extraction } from "@/lib/types"
import { cn } from "@/lib/utils"
import { Download, FileText, File, Eye, EyeOff, RefreshCw, Loader2 } from "lucide-react"

interface DownloadSectionProps {
  extraction: Extraction
  researchResult: string
  exportResult: ExportResult | null
  onExport: (format: "markdown" | "pdf" | "both") => Promise<void>
  onStartNew: () => void
  isExporting: boolean
}

export function DownloadSection({
  extraction,
  researchResult,
  exportResult,
  onExport,
  onStartNew,
  isExporting,
}: DownloadSectionProps) {
  const [showPreview, setShowPreview] = useState(true)
  const [exportFormat, setExportFormat] = useState<"markdown" | "pdf" | "both">("both")

  const handleExport = async () => {
    await onExport(exportFormat)
  }

  return (
    <div className="w-full max-w-4xl mx-auto space-y-6">
      <div className="text-center space-y-2">
        <h2 className="text-2xl font-semibold">Research Complete</h2>
        <p className="text-muted-foreground">
          {extraction.organization} - {extraction.project_title}
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-center gap-4">
        <button
          type="button"
          onClick={() => setShowPreview(!showPreview)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg border border-border hover:bg-muted transition-colors"
        >
          {showPreview ? (
            <EyeOff className="h-4 w-4" />
          ) : (
            <Eye className="h-4 w-4" />
          )}
          {showPreview ? "Hide Preview" : "Show Preview"}
        </button>

        <div className="flex items-center gap-2 p-1 bg-muted rounded-lg">
          <button
            type="button"
            onClick={() => setExportFormat("markdown")}
            className={cn(
              "px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
              exportFormat === "markdown"
                ? "bg-primary text-primary-foreground"
                : "hover:bg-background"
            )}
          >
            Markdown
          </button>
          <button
            type="button"
            onClick={() => setExportFormat("pdf")}
            className={cn(
              "px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
              exportFormat === "pdf"
                ? "bg-primary text-primary-foreground"
                : "hover:bg-background"
            )}
          >
            PDF
          </button>
          <button
            type="button"
            onClick={() => setExportFormat("both")}
            className={cn(
              "px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
              exportFormat === "both"
                ? "bg-primary text-primary-foreground"
                : "hover:bg-background"
            )}
          >
            Both
          </button>
        </div>

        <button
          type="button"
          onClick={handleExport}
          disabled={isExporting}
          className="flex items-center gap-2 px-6 py-2 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isExporting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          {isExporting ? "Generating..." : "Generate & Download"}
        </button>
      </div>

      {exportResult && (
        <div className="flex flex-wrap items-center justify-center gap-4 p-4 bg-success/10 border border-success/30 rounded-lg">
          {exportResult.markdownUrl && (
            <a
              href={exportResult.markdownUrl}
              download
              className="flex items-center gap-2 px-4 py-2 bg-card border border-border rounded-lg hover:bg-muted transition-colors"
            >
              <FileText className="h-4 w-4 text-primary" />
              Download Markdown
            </a>
          )}
          {exportResult.pdfUrl && (
            <a
              href={exportResult.pdfUrl}
              download
              className="flex items-center gap-2 px-4 py-2 bg-card border border-border rounded-lg hover:bg-muted transition-colors"
            >
              <File className="h-4 w-4 text-destructive" />
              Download PDF
            </a>
          )}
        </div>
      )}

      {showPreview && (
        <div className="border border-border rounded-xl overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 bg-muted/50 border-b border-border">
            <span className="text-sm font-medium">Research Report Preview</span>
          </div>
          <div className="p-6 max-h-[600px] overflow-y-auto bg-card markdown-preview">
            <ReactMarkdown>{researchResult}</ReactMarkdown>
          </div>
        </div>
      )}

      <div className="flex justify-center pt-4">
        <button
          type="button"
          onClick={onStartNew}
          className="flex items-center gap-2 px-6 py-2 border border-border rounded-lg hover:bg-muted transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          Start New Research
        </button>
      </div>
    </div>
  )
}
