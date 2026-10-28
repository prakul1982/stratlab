/* My space's cards, their order and which are shown (kept apart from the data so it can be tested without the app). */

export const CARDS = [
  { id: "networth", label: "Net worth" },
  { id: "pnl", label: "Your P&L" },
  { id: "paper", label: "Paper sessions" },
  { id: "markets", label: "Markets" },
  { id: "coming", label: "Coming up" },
  { id: "watch", label: "Your watchlist today" },
] as const;
export type CardId = (typeof CARDS)[number]["id"];
export interface Layout { order: CardId[]; hidden: CardId[] }
export const DEFAULT_LAYOUT: Layout = { order: CARDS.map((c) => c.id), hidden: [] };

/** A saved layout made safe: unknown cards dropped, cards added since appended, no repeats. */
export function cleanLayout(raw: unknown): Layout {
  const ids = CARDS.map((c) => c.id) as string[];
  const r = (raw && typeof raw === "object" ? raw : {}) as Partial<Record<keyof Layout, unknown>>;
  const list = (x: unknown) => (Array.isArray(x) ? x.filter((v): v is CardId => typeof v === "string" && ids.includes(v)) : []);
  const order = [...new Set(list(r.order))];
  for (const id of ids) if (!order.includes(id as CardId)) order.push(id as CardId);
  return { order, hidden: [...new Set(list(r.hidden))] };
}

/** How wide each card would like to be on a wide screen, out of 12 columns. */
const WANT: Record<CardId, number> = { networth: 4, pnl: 4, paper: 4, markets: 12, coming: 7, watch: 5 };

/** Each shown card's width (of 12) on a wide screen, from its place in the person's order: cards go into rows in that order,
 * and a row a card no longer fits in is closed and its cards widened to fill it. The grid used to fill gaps by itself and
 * moved a card the person had put second below the two after it, leaving a hole in the first row (DI-005). `alone` names cards
 * that always take a row of their own. */
export function slotSpans(shown: CardId[], alone: CardId[] = []): Record<string, number> {
  const out: Record<string, number> = {};
  let row: CardId[] = [], used = 0;
  const close = () => {
    if (!row.length) return;
    let left = 12;
    row.forEach((id, n) => {
      const w = n === row.length - 1 ? left : Math.round((WANT[id] * 12) / used);
      out[id] = w;
      left -= w;
    });
    row = []; used = 0;
  };
  for (const id of shown) {
    // a card with nothing to list (an empty watchlist) takes a row of its own, so it never stands beside a long list with blank space under it (VR6-010)
    if (alone.includes(id)) { close(); row = [id]; used = 12; close(); continue; }
    const w = WANT[id] ?? 12;
    if (used + w > 12) close();
    row.push(id); used += w;
  }
  close();
  return out;
}

/** A results day as one line whichever calendar it came from: "AAVAS results · Among your stocks", the purpose only when it
 * adds something ("Financial Results/Other business matters" said "results" twice, DI-009). */
export function resultsLine(symbol: string, purpose: string | null | undefined, when?: string | null): { title: string; detail: string } {
  const extra = String(purpose ?? "").replace(/\b(quarterly |financial |audited |unaudited )?results?\b(\s*(and|&|\/)\s*)?/gi, "").replace(/^[\s/,&-]+|[\s/,&-]+$/g, "").trim();
  return { title: `${symbol} results`, detail: ["Among your stocks", extra || null, when || null].filter(Boolean).join(" · ") };
}
