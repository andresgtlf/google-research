import type { ProviderInfo } from "../types";
import { Badge } from "./Badge";

const TIER_LABELS: Record<string, string> = {
  fast: "Fast",
  max: "Max depth",
  legacy: "Legacy",
};

interface ProviderPickerProps {
  providers: ProviderInfo[];
  selected: string;
  tier: string;
  onSelect: (id: string) => void;
  onTier: (tier: string) => void;
}

/**
 * Radio cards with a real `<input type="radio">` underneath each (spec
 * Section 6): visually a styled card, but a screen reader and keyboard
 * user get a genuine radio group, not a div pretending to be one.
 */
export default function ProviderPicker({
  providers,
  selected,
  tier,
  onSelect,
  onTier,
}: ProviderPickerProps) {
  const current = providers.find((p) => p.id === selected);
  const tiers = current ? [...new Set(current.models.map((m) => m.tier))] : [];
  const activeModel = current?.models.find((m) => m.tier === tier) ?? current?.models[0];

  return (
    <div>
      <div className="mb-2 text-label text-[var(--color-text-secondary)]">
        Research engine
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {providers.map((p) => {
          const isSelected = selected === p.id;
          return (
            <label
              key={p.id}
              className={`relative cursor-pointer rounded-lg border p-4 transition-colors duration-150 ${
                isSelected
                  ? "border-[var(--color-accent)] bg-[var(--color-accent-subtle)] ring-1 ring-[var(--color-accent)]/20"
                  : "border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] hover:border-[var(--color-border-strong)]"
              }`}
            >
              <input
                type="radio"
                name="provider"
                value={p.id}
                checked={isSelected}
                onChange={() => { onSelect(p.id); onTier(p.recommended_tier ?? "fast"); }}
                className="sr-only"
              />
              {isSelected && (
                <span className="absolute right-3 top-3 h-2.5 w-2.5 rounded-full bg-[var(--color-accent)]" />
              )}
              <div className="text-h3 text-[var(--color-text-primary)]">{p.label}</div>
              {!p.available && (
                <div className="mt-1">
                  <Badge tone="warning">Needs API key</Badge>
                </div>
              )}
              <p className="mt-1.5 text-caption text-[var(--color-text-secondary)]">
                {p.description}
              </p>
            </label>
          );
        })}
      </div>

      {current && !current.available && (
        <div className="mt-3 rounded-lg border border-[var(--color-warning)]/25 bg-[var(--color-warning-bg)] px-3 py-2 text-caption text-[var(--color-warning-text)]">
          Requires <code className="font-mono">{current.env_key}</code>. See
          API_KEYS.md for setup instructions.
        </div>
      )}

      {current && tiers.length > 0 && (
        <div className="mt-3">
          <label className="mb-2 block text-label text-[var(--color-text-secondary)]">
            Model
          </label>
          <select
            value={tier}
            onChange={(e) => onTier(e.target.value)}
            className="w-full rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] px-3 py-2 text-body text-[var(--color-text-primary)] focus:border-[var(--color-accent)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/15"
          >
            {tiers.map((t) => {
              const model = current.models.find((m) => m.tier === t);
              return (
                <option key={t} value={t}>
                  {model?.label ?? TIER_LABELS[t] ?? t}
                  {model ? ` (${model.id})` : ""}
                </option>
              );
            })}
          </select>
          {activeModel?.note && (
            <p className="mt-1.5 text-caption text-[var(--color-text-tertiary)]">
              {activeModel.note}
            </p>
          )}
        </div>
      )}

      <p className="mt-2 text-caption text-[var(--color-text-tertiary)]">
        Choose the model that will run the deep-research job. This cannot be
        changed once research starts.
      </p>
    </div>
  );
}
