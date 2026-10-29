/* Market Watch's calls to the server (MW-1) and the page's one live client. Account code: the public half never imports it. */
import { api } from "./api";
import { LiveClient, type Transport } from "./watchLive";
import type { WatchItem, WatchLimits, WatchList, WatchQuote } from "./watch";

export interface WatchAnswer { lists: WatchList[]; limits: WatchLimits }

export const getLists = () => api<WatchAnswer>("/watch/lists");
export const createList = (name: string) => api<WatchAnswer>("/watch/lists", { method: "POST", body: { name } });
export const renameList = (id: string, name: string) => api<WatchAnswer>(`/watch/lists/${encodeURIComponent(id)}`, { method: "PATCH", body: { name } });
export const deleteList = (id: string) => api<WatchAnswer>(`/watch/lists/${encodeURIComponent(id)}`, { method: "DELETE" });
export const putItems = (id: string, items: WatchItem[]) => api<WatchAnswer>(`/watch/lists/${encodeURIComponent(id)}/items`, { method: "PUT", body: { items } });
export const putOrder = (ids: string[]) => api<WatchAnswer>("/watch/order", { method: "PUT", body: { ids } });

const ids = (keys: string[]) => encodeURIComponent(keys.join(","));

export async function getQuotes(keys: string[]): Promise<Record<string, WatchQuote | null>> {
  return (await api<{ quotes: Record<string, WatchQuote | null> }>(`/watch/quotes?ids=${ids(keys)}`)).quotes ?? {};
}

/** Lines of recent closes for the rows, kept on this page for 30 minutes (the server keeps them as long). A line being read is
 * read once: the panel asks again for the rows in view each time its list of them changes, and each ask used to start its own read
 * of every line still on its way (MWR1-014: five reads of the same seven lines in the first seconds). */
const sparkKept = new Map<string, { at: number; v: number[] }>();
const sparkWait = new Map<string, Promise<number[] | undefined>>();
export async function getSparks(keys: string[]): Promise<Record<string, number[]>> {
  const now = Date.now(), out: Record<string, number[]> = {}, need: string[] = [], waits: [string, Promise<number[] | undefined>][] = [];
  for (const k of keys) {
    const hit = sparkKept.get(k);
    if (hit && now - hit.at < 30 * 60_000) out[k] = hit.v;
    else if (sparkWait.has(k)) waits.push([k, sparkWait.get(k)!]);
    else need.push(k);
  }
  if (need.length) {
    const read = api<{ sparks: Record<string, number[]> }>(`/watch/spark?ids=${ids(need)}`).then((r) => r.sparks ?? {});
    for (const k of need) {
      const one = read.then((got) => got[k], () => undefined);
      sparkWait.set(k, one);
      waits.push([k, one]);
    }
    read.then(() => undefined, () => undefined).then(() => { for (const k of need) sparkWait.delete(k); });
    try { await read; } catch (e) { if (!waits.length) throw e; }
  }
  for (const [k, w] of waits) {
    const v = await w;
    if (v) {
      sparkKept.set(k, { at: now, v }); out[k] = v;
      if (sparkKept.size > 300) sparkKept.delete(sparkKept.keys().next().value!);
    }
  }
  return out;
}

const transport: Transport = {
  open: (keys, signal) => api<Response>(`/watch/stream?ids=${ids(keys)}`, { raw: true, signal }),
  quotes: getQuotes,
};

let client: LiveClient | null = null;
/** The page's one live client: every chart and the panel share its stream and its reads. */
export const live = (): LiveClient => (client ??= new LiveClient(transport));
