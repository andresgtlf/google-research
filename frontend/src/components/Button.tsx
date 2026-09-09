import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "tertiary";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const BASE =
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-body font-medium transition-colors duration-150 disabled:cursor-not-allowed";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-[var(--color-accent)] text-white px-5 py-2.5 hover:bg-[var(--color-accent-hover)] active:bg-[var(--color-accent-active)] active:scale-[0.98] disabled:bg-[var(--color-border-strong)] disabled:text-[var(--color-text-tertiary)] disabled:active:scale-100",
  secondary:
    "bg-[var(--color-surface-1)] border border-[var(--color-border-strong)] text-[var(--color-text-primary)] px-5 py-2.5 hover:border-[var(--color-accent)]/50 hover:bg-[var(--color-accent-subtle)] disabled:bg-[var(--color-surface-2)] disabled:text-[var(--color-text-tertiary)] disabled:border-[var(--color-border-subtle)]",
  tertiary:
    "text-[var(--color-accent)] underline-offset-2 hover:underline px-1 disabled:text-[var(--color-text-tertiary)]",
};

/** Same classes as <Button>, for the rare case a link needs to look like
 * one (file downloads render as <a> so the browser's native download/open
 * behavior and right-click menu keep working). */
export function buttonClasses(variant: Variant = "primary", className = ""): string {
  return `${BASE} ${VARIANTS[variant]} ${className}`;
}

/**
 * Single source of truth for the app's three-tier button hierarchy (spec
 * Section 6, "Button hierarchy"). Using this everywhere is what keeps the
 * corner-radius and interaction-state rules from drifting per-component.
 */
export default function Button({
  variant = "primary",
  className = "",
  ...rest
}: ButtonProps) {
  return (
    <button className={`${BASE} ${VARIANTS[variant]} ${className}`} {...rest} />
  );
}
