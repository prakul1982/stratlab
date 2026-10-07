import { useEffect, useState } from "react";
import { api } from "./api";
import { fmtDate } from "./format";

/** The market events calendar (RBI policy, India's data releases, the US Fed and data, index changes, expiries and
 * holidays): one answer for the Events page, the Invest home's next events and the index badges on company pages, read
 * once and kept for ten minutes. */
export type EvKind = "rbi" | "india" | "us" | "budget" | "index" | "expiry" | "holiday";
export interface MarketEvent {
  id: string; kind: EvKind; date: string; time: string | null; title: string; detail: string; figure: string | null;
  previous: string | null; url: string | null; status: "scheduled" | "released" | "awaiting"; symbols?: string[]; change?: string; custom?: string;
}
export interface IndexSection { index: string; in: [string, string][]; out: [string, string][] }
export interface IndexChange { id: string; url: string; title: string; announced: string; effective: string | null; sections: IndexSection[] }
export interface IndexBadge { short: string; text: string; date: string; index: string; way: "in" | "out" }
export interface EvSource { id: string; label: string; as_of: string | null; checked: string | null; failed: boolean }
export interface EvPrefs {
  remind: boolean; kinds: EvKind[]; days: number; money_calendar: boolean; allowed: boolean; plan: string; channels: string[]; remind_days: number[];
}
export interface EventsView {
  events: MarketEvent[]; index_changes: IndexChange[]; badges: Record<string, IndexBadge[]>; sources: EvSource[]; as_of: string | null;
  kinds: Record<EvKind, string>; today: string; note: string; prefs: EvPrefs; week: { results: number | null; actions: number | null };
  custom_kinds: Record<string, string>;
}

let cached: { at: number; p: Promise<EventsView | null> } | null = null;

export function loadEvents(fresh = false): Promise<EventsView | null> {
  if (fresh || !cached || Date.now() - cached.at > 10 * 60_000) {
    const p = api<EventsView>("/trade/events").catch(() => { cached = null; return null; });
    cached = { at: Date.now(), p };
  }
  return cached.p;
}

/** The calendar, once loaded (null until then, or when it can't be read). `on` false skips the call. */
export function useEvents(on = true): EventsView | null {
  const [v, setV] = useState<EventsView | null>(null);
  useEffect(() => {
    if (!on) return;
    let live = true;
    loadEvents().then((x) => live && setV(x));
    return () => { live = false; };
  }, [on]);
  return v;
}

/** "Wed 7 Oct" for an ISO day. */
export function evDay(iso: string, year = false): string {
  return fmtDate(iso, { weekday: true, year });
}
