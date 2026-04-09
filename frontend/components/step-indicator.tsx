"use client"

import { cn } from "@/lib/utils"
import type { Step } from "@/lib/types"
import { Upload, FileSearch, Search, Download, Check } from "lucide-react"

const steps: { key: Step; label: string; icon: typeof Upload }[] = [
  { key: "upload", label: "Upload", icon: Upload },
  { key: "extract", label: "Extract", icon: FileSearch },
  { key: "research", label: "Research", icon: Search },
  { key: "download", label: "Download", icon: Download },
]

interface StepIndicatorProps {
  currentStep: Step
}

export function StepIndicator({ currentStep }: StepIndicatorProps) {
  const currentIndex = steps.findIndex((s) => s.key === currentStep)

  return (
    <div className="flex items-center justify-center gap-2 sm:gap-4">
      {steps.map((step, index) => {
        const isCompleted = index < currentIndex
        const isCurrent = step.key === currentStep
        const Icon = step.icon

        return (
          <div key={step.key} className="flex items-center">
            <div className="flex flex-col items-center gap-2">
              <div
                className={cn(
                  "flex h-10 w-10 items-center justify-center rounded-full border-2 transition-all duration-300",
                  isCompleted && "border-success bg-success text-success-foreground",
                  isCurrent && "border-primary bg-primary text-primary-foreground",
                  !isCompleted && !isCurrent && "border-muted-foreground/30 text-muted-foreground/50"
                )}
              >
                {isCompleted ? (
                  <Check className="h-5 w-5" />
                ) : (
                  <Icon className="h-5 w-5" />
                )}
              </div>
              <span
                className={cn(
                  "text-xs font-medium transition-colors",
                  isCompleted && "text-success",
                  isCurrent && "text-primary",
                  !isCompleted && !isCurrent && "text-muted-foreground/50"
                )}
              >
                {step.label}
              </span>
            </div>
            {index < steps.length - 1 && (
              <div
                className={cn(
                  "mx-2 h-0.5 w-8 sm:w-12 lg:w-16 transition-colors",
                  index < currentIndex ? "bg-success" : "bg-muted-foreground/20"
                )}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
