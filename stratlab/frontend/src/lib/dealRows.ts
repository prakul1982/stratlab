/* How the deals table reads its rows (components/Deals.tsx): no browser needed, so the unit tests read them. */

type DealLike = { kind: string; date: string; qty: number | null; price: number | null; side: string; who: string };

/** A bulk or block deal's two sides (the same day, shares and price, one buyer and one seller) as one row, the buyer with
 * "from" the seller, not two rows that say the same trade twice (DD-021). Everything else as it is. */
export function pairDeals<T extends DealLike>(items: T[]): (T & { from?: string })[] {
  const pairs = (d: T) => (d.kind === "bulk" || d.kind === "block") && d.qty != null;
  const key = (d: T) => `${d.kind}|${d.date.slice(0, 10)}|${d.qty}|${d.price}`;
  const groups = new Map<string, T[]>();
  for (const d of items) if (pairs(d)) groups.set(key(d), [...(groups.get(key(d)) ?? []), d]);
  const out: (T & { from?: string })[] = [];
  for (const d of items) {
    const g = pairs(d) ? groups.get(key(d)) : undefined;
    const buy = g?.filter((x) => x.side === "bought") ?? [], sell = g?.filter((x) => x.side === "sold") ?? [];
    if (g && g.length === 2 && buy.length === 1 && sell.length === 1) {
      if (d === buy[0]) out.push({ ...d, from: sell[0].who });         // the pair is shown once, at the buyer's place
      continue;
    }
    out.push(d);
  }
  return out;
}

/** "0.42% after", "under 0.01% after", or nothing when the filing gives no stake after (a 0 is a blank, not a holding:
 * DD-021's "0.00% after" on every insider row). */
export function afterText(pct: number | null | undefined): string | null {
  if (pct == null || !(pct > 0)) return null;
  return pct < 0.01 ? "under 0.01% after" : `${pct.toFixed(2)}% after`;
}
