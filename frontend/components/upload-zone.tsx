"use client"

import { useCallback, useState } from "react"
import { useDropzone } from "react-dropzone"
import { cn, formatBytes } from "@/lib/utils"
import { Upload, FileText, X, Loader2 } from "lucide-react"

interface UploadZoneProps {
  onUpload: (file: File) => Promise<void>
  isLoading: boolean
}

export function UploadZone({ onUpload, isLoading }: UploadZoneProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      setError(null)
      const file = acceptedFiles[0]

      if (!file) return

      if (file.type !== "application/pdf") {
        setError("Please upload a PDF file")
        return
      }

      if (file.size > 20 * 1024 * 1024) {
        setError("File size must be less than 20MB")
        return
      }

      setSelectedFile(file)
    },
    []
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
    },
    maxFiles: 1,
    disabled: isLoading,
  })

  const handleSubmit = async () => {
    if (!selectedFile) return
    try {
      await onUpload(selectedFile)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed")
    }
  }

  const clearFile = () => {
    setSelectedFile(null)
    setError(null)
  }

  return (
    <div className="w-full max-w-2xl mx-auto space-y-4">
      <div
        {...getRootProps()}
        className={cn(
          "relative flex flex-col items-center justify-center gap-4 rounded-xl border-2 border-dashed p-8 sm:p-12 transition-all cursor-pointer",
          isDragActive && "border-primary bg-primary/5",
          !isDragActive && !selectedFile && "border-muted-foreground/30 hover:border-primary/50 hover:bg-muted/50",
          selectedFile && "border-success/50 bg-success/5",
          isLoading && "pointer-events-none opacity-60"
        )}
      >
        <input {...getInputProps()} />

        {isLoading ? (
          <>
            <Loader2 className="h-12 w-12 text-primary animate-spin" />
            <div className="text-center">
              <p className="text-lg font-medium">Processing document...</p>
              <p className="text-sm text-muted-foreground mt-1">
                Extracting information from your concept note
              </p>
            </div>
          </>
        ) : selectedFile ? (
          <>
            <FileText className="h-12 w-12 text-success" />
            <div className="text-center">
              <p className="text-lg font-medium">{selectedFile.name}</p>
              <p className="text-sm text-muted-foreground">
                {formatBytes(selectedFile.size)}
              </p>
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                clearFile()
              }}
              className="absolute top-4 right-4 p-1 rounded-full hover:bg-muted transition-colors"
            >
              <X className="h-5 w-5 text-muted-foreground" />
            </button>
          </>
        ) : (
          <>
            <Upload className="h-12 w-12 text-muted-foreground" />
            <div className="text-center">
              <p className="text-lg font-medium">
                {isDragActive ? "Drop your PDF here" : "Drag & drop your concept note"}
              </p>
              <p className="text-sm text-muted-foreground mt-1">
                or click to browse files
              </p>
            </div>
          </>
        )}
      </div>

      {error && (
        <div className="flex items-center justify-center gap-2 text-destructive text-sm">
          <X className="h-4 w-4" />
          <span>{error}</span>
        </div>
      )}

      <div className="flex flex-col items-center gap-3">
        <p className="text-xs text-muted-foreground">
          Supported: PDF files up to 20MB
        </p>

        {selectedFile && !isLoading && (
          <button
            type="button"
            onClick={handleSubmit}
            className="px-6 py-2.5 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 transition-colors"
          >
            Extract Information
          </button>
        )}
      </div>
    </div>
  )
}
