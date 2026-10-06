/* My space's cards, their order and which are shown (kept apart from the data so it can be tested without the app). */

export const CARDS = [
  { id: "networth", label: "Net worth" },
  { id: "pnl", label: "Today's P&L" },
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
