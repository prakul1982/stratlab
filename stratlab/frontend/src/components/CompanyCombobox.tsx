import { api } from "../lib/api";

export type Suggestion = { symbol: string; id: string; name: string; exchange: string; market: "IN" | "US" };
export type Market = "IN" | "US" | "ALL";

const cache = new Map<string, Suggestion[]>();

/** Listed companies for what's typed, up to 8 (the same answer is reused while the page is open). */
export async function suggestions(q: string, market: Market): Promise<Suggestion[]> {
  const key = `${market}:${q.toUpperCase()}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const r = await api<{ rows: Suggestion[] }>(`/suggest/companies?q=${encodeURIComponent(q)}${market === "ALL" ? "" : `&market=${market}`}`);
  if (cache.size > 300) cache.clear();
  cache.set(key, r.rows);
  return r.rows;
}
