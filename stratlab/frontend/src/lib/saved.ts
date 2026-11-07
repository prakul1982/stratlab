/* Saved searches and AI reads (R19): the account's list, shared by every page that shows it (a Save button and the list beside it stay in
 * step), and how each kind is read again for Update: through the page's own endpoint, so the read follows that endpoint's cache rules (no
 * extra AI call while a fresh read is kept). Signed-in pages only: nothing here is in the landing chunk. */
import { useEffect, useState } from "react";
import { api } from "./api";
import { useApp } from "./app";
import { researchApi, type Region } from "./research";
import { filingsSnap, readSnap, themeReady, themeSnap, type Changes, type FilingsOut, type SavedItem, type SavedKind, type Snap } from "./savedSnap";

export type { SavedItem, SavedKind, Snap, Changes } from "./savedSnap";
export interface SavedPage { items: SavedItem[]; count: number; limit: number }

let cache: SavedPage | null = null;
let cacheFor = "";            // whose list the copy is: another person signing in on this tab reads their own
let loading: Promise<SavedPage> | null = null;
const subs = new Set<(p: SavedPage) => void>();
const publish = (p: SavedPage) => { cache = p; subs.forEach((f) => f(p)); return p; };

/** The whole list (every kind) once; a second caller waits for the same read. */
function load(again = false): Promise<SavedPage> {
  if (cache && !again) return Promise.resolve(cache);
  if (!loading) loading = api<SavedPage>("/me/saved").then(publish).finally(() => { loading = null; });
  return loading;
}

/** The account's saved items (of one kind, or all), kept in step across the page; `failed` when the list couldn't be read. */
export function useSaved(kind?: SavedKind, on = true) {
  const uid = useApp().me?.id ?? "";
  if (uid !== cacheFor) { cacheFor = uid; cache = null; }
  on = on && !!uid;
  const [page, setPage] = useState<SavedPage | null>(cache);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!on) return;
    subs.add(setPage);
    load().then(setPage).catch(() => setFailed(true));
    return () => { subs.delete(setPage); };
  }, [on, uid]);
  const items = page ? page.items.filter((x) => !kind || x.kind === kind) : null;
  return { items, count: page?.count ?? 0, limit: page?.limit ?? 25, failed };
}

/** The whole list again, from what the server answered with (every write answers with its kind's list, so the list is read once more). */
const refreshAll = () => load(true).catch(() => cache);

export const savedApi = {
  /** {count, limit}: the saved list's use of its limit (Settings' usage table reads it). */
  usage: () => api<{ count: number; limit: number }>("/me/saved/usage"),
  save: async (kind: SavedKind, name: string, params: Record<string, string>, snap: Snap | null) => {
    const r = await api<{ item: SavedItem; new: boolean }>("/me/saved", { method: "POST", body: { kind, name, params, snap } });
    await refreshAll();
    return r;
  },
  rename: async (id: string, name: string) => { const r = await api<{ item: SavedItem }>(`/me/saved/${id}`, { method: "PATCH", body: { name } }); await refreshAll(); return r.item; },
  remove: async (id: string) => { await api(`/me/saved/${id}`, { method: "DELETE" }); await refreshAll(); },
  update: async (id: string, snap: Snap) => {
    const r = await api<{ item: SavedItem; changes: Changes | null }>(`/me/saved/${id}/update`, { method: "POST", body: { snap } });
    await refreshAll();
    return r;
  },
};

/** The same search as a saved one: one kind, the same parameters (a Save button then says "Saved"). */
export const sameSearch = (a: Record<string, string>, b: Record<string, string>) => {
  const ka = Object.keys(a).filter((k) => a[k]), kb = Object.keys(b).filter((k) => b[k]);
  return ka.length === kb.length && ka.every((k) => String(a[k]) === String(b[k]));
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const isoDay = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const daysBack = (n: number) => { const d = new Date(); d.setDate(d.getDate() - n); return isoDay(d); };
export const THEME_TRIES = 18, THEME_EVERY_MS = 5000;     // as the Themes page asks while a read is written: every 5 s for 90 s

/** A saved item read again through its page's own endpoint, as a snapshot; null while the read is still being written (try again later). */
export async function readSaved(item: Pick<SavedItem, "kind" | "params">, every = THEME_EVERY_MS): Promise<Snap | null> {
  const p = item.params;
  const region = (p.region === "US" ? "US" : "IN") as Region;
  switch (item.kind) {
    case "theme":
      for (let i = 0; i < THEME_TRIES; i++) {
        const r = await researchApi.sector(region, p.q);
        if (themeReady(r)) return themeSnap(r);
        await sleep(every);
      }
      return null;
    case "filings": {
      const custom = p.range === "custom";
      const qs = new URLSearchParams({ region, scope: p.view === "mine" ? "mine" : "all", flag: p.flag ?? "", frm: custom ? p.frm ?? "" : daysBack(Number(p.range) || 90),
        to: custom ? p.to ?? "" : "", q: p.q ?? "", page: "1", size: "100" });
      return filingsSnap(await api<FilingsOut>(`/research/redflags?${qs}`));
    }
    case "company_ai": return readSnap((await researchApi.companyAI(region, p.symbol)).generated_at);
    case "compare": return readSnap((await researchApi.compare(region, p.a, p.b)).ai?.generated_at ?? null);
    case "deep_dive": return null;
  }
}
