/* "Test an idea on X": finding the instrument a hand-over names. No imports from the app, so it can be tested alone. */
import type { Instrument } from "./types";

export type Prefill = { market: string; symbol?: string; instrumentId?: string | null; text?: string };
type Get = <T>(path: string) => Promise<T>;

/** The id to look up directly: the one handed over, else a US ticker's own id ("US:F"). Search needs two letters, so
 *  it can't find a one-letter ticker; India's ids are exchange tokens, so those go through search. */
export function directId(p: Prefill): string | null {
  if (p.instrumentId) return p.instrumentId;
  if (p.market === "US" && p.symbol && /^[A-Za-z0-9.-]{1,20}$/.test(p.symbol)) return `US:${p.symbol.toUpperCase()}`;
  return null;
}

/** The instrument for a prefill, or null when nothing matches. A chosen contract (an id) is kept as it is. */
export async function findPrefill(p: Prefill, get: Get): Promise<Instrument | null> {
  const id = directId(p);
  if (id) {
    try { return await get<Instrument>(`/instruments/${encodeURIComponent(id)}`); } catch { if (p.instrumentId) return null; }
  }
  if (!p.symbol || p.symbol.length < 2) return null;
  try {
    const rows = await get<Instrument[]>(`/instruments/search?q=${encodeURIComponent(p.symbol)}&market=${p.market}`);
    return rows.find((r) => r.symbol.toUpperCase() === p.symbol!.toUpperCase() && !r.fno) ?? null;
  } catch { return null; }
}
