import { useEffect, useState } from "react";
import { api } from "./api";
import type { Usage } from "./usageText";

/* A person's limits, one call (GET /me/usage, R19): Settings' "Your usage" table and the note beside every Refresh button read it.
 * Kept here once per page load and read again after a Refresh (usageChanged), so the "left today" note goes down at once. */

/** What a Refresh of a stored shared read did (the server's "refresh_state"). */
export type RefreshState = "fresh" | "capped" | "failed" | "started" | "done";

export type { Usage, UsageRow } from "./usageText";

let kept: Promise<Usage> | null = null;
const listeners = new Set<() => void>();

export function loadUsage(): Promise<Usage> {
  if (!kept) {
    kept = api<Usage>("/me/usage");
    kept.catch(() => { kept = null; });
  }
  return kept;
}

/** After a Refresh (or anything that counts): read again, and every note on the page shows the new count. */
export function usageChanged(): void {
  kept = null;
  listeners.forEach((f) => f());
}

export function useUsage(): { usage: Usage | null; error: string | null } {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [n, setN] = useState(0);
  useEffect(() => {
    const bump = () => setN((x) => x + 1);
    listeners.add(bump);
    return () => { listeners.delete(bump); };
  }, []);
  useEffect(() => {
    let live = true;
    loadUsage().then((u) => { if (live) { setUsage(u); setError(null); } }).catch((e) => live && setError((e as Error).message));
    return () => { live = false; };
  }, [n]);
  return { usage, error };
}

export { refreshesLeft, resetsWord, usedWord } from "./usageText";
