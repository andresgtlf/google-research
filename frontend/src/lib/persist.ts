import type { PersistedAppState } from "../types";

const STORAGE_KEY = "gtlf-research-state-v1";

/** Read the persisted wizard state. Returns null on first visit, on a
 * corrupt value, or when storage is unavailable (private browsing, etc.) -
 * never throws. */
export function loadPersistedState(): PersistedAppState | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return parsed as PersistedAppState;
  } catch {
    return null;
  }
}

export function savePersistedState(state: PersistedAppState): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* storage unavailable or full. The app still works, it just will not
     * survive a refresh. Not worth surfacing to the user. */
  }
}

export function clearPersistedState(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
