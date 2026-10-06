import { useEffect, useState } from "react";
import { api } from "./api";

/** F&O contract changes (the exchange's contract file and circulars): the dated list, and one answer for every badge in
 * the app ("Leaves F&O after 28 Jul", "Lot 75→65 from 31 Dec"), read once and kept for ten minutes. */
export type FoKind = "exit" | "entry" | "lot" | "expiry" | "circular";
export interface FoEvent {
  id: string; kind: FoKind; symbol: string | null; symbols?: string[] | null; segment?: "index" | "stock" | null; series?: string | null;
  series_label?: string | null; expiry?: string | null; effective?: string | null; was?: number | null; now?: number | null; lot?: number | null;
  seen?: string | null; source?: string | null; no?: string | null; subject?: string | null; within?: boolean | null;
  date: string; text: string; upcoming: boolean;
  /** the circulars (and the contract file) the change rests on */
  sources?: { no: string; subject: string; url: string; date?: string | null }[];
}
export interface FoBadge { kind: FoKind; short: string; text: string; date: string }
export interface FoSource { id: string; label: string; as_of: string | null; checked: string | null; failed: boolean }
export interface FoView {
  events: FoEvent[]; badges: Record<string, FoBadge[]>; sources: FoSource[]; as_of: string | null; note: string; kinds: Record<FoKind, string>;
  today: string; mine: string[]; alerts: { on: boolean; allowed: boolean; plan: string; channels: string[] };
}

let cached: { at: number; p: Promise<FoView | null> } | null = null;

export function loadFoChanges(fresh = false): Promise<FoView | null> {
  if (fresh || !cached || Date.now() - cached.at > 10 * 60_000) {
    const p = api<FoView>("/trade/fo-changes").catch(() => { cached = null; return null; });
    cached = { at: Date.now(), p };
  }
  return cached.p;
}

/** The changes, once loaded (null until then, or when they can't be read). `on` false skips the call. */
export function useFoChanges(on = true): FoView | null {
  const [v, setV] = useState<FoView | null>(null);
  useEffect(() => {
    if (!on) return;
    let live = true;
    loadFoChanges().then((x) => live && setV(x));
    return () => { live = false; };
  }, [on]);
  return v;
}

/** The F&O underlying a paper session trades: an options session's underlying, a future's name, else the symbol. */
export function foSymbol(i: { underlying?: string; name?: string; symbol?: string; fno?: boolean } | null | undefined): string {
  return ((i?.underlying || (i?.fno ? i?.name : i?.symbol)) ?? "").toUpperCase();
}
