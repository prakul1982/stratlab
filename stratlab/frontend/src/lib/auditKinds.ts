/** Admin → Quality: the audit's findings of one level counted by kind (LIVE4-017: 3,557 document facts were plain rows, one per company,
 * and nothing said how many companies had which). A finding's kind is its wording with its own numbers and names taken out: the text
 * before its first ":" (the explanation after it is the same for all), each number made "N". */
export type KindRow = { area: string; kind: string; companies: number };

export function kindOf(detail: string): string {
  const head = detail.split(/:\s/)[0];
  return head.replace(/\d[\d,.]*/g, "N").replace(/\s+/g, " ").trim();
}

export function kindsOf(rows: { symbol: string; issues: { level: string; area: string; detail: string }[] }[], level: string, top = 12): KindRow[] {
  const by = new Map<string, { area: string; kind: string; who: Set<string> }>();
  for (const r of rows) for (const i of r.issues) {
    if (level !== "all" && i.level !== level) continue;
    const kind = kindOf(i.detail), key = `${i.area}\u0000${kind}`;
    const got = by.get(key) ?? { area: i.area, kind, who: new Set<string>() };
    got.who.add(r.symbol);
    by.set(key, got);
  }
  return [...by.values()].map((x) => ({ area: x.area, kind: x.kind, companies: x.who.size }))
    .sort((a, b) => b.companies - a.companies || a.area.localeCompare(b.area) || a.kind.localeCompare(b.kind)).slice(0, top);
}
