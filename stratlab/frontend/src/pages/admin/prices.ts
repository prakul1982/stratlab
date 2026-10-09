/* Admin → Money → Prices: what the exchange-rate line says (R7M-003). A currency whose rate couldn't be read is either one the
 * last rate is kept for, or one that never had a rate: its price is then only a built-in default, and visitors aren't shown it. */

/** The currencies that follow the rupee price but have no exchange rate to follow (the server marks them `no_rate`). */
export function noRate(rows: Record<string, { no_rate?: boolean }> | null | undefined): string[] {
  return Object.entries(rows ?? {}).filter(([, r]) => r.no_rate).map(([c]) => c);
}

/** The sentence after "Exchange rates read …": which couldn't be read with the last rate kept, and which have no rate at all. */
export function rateNote(errors: string[], rows: Record<string, { no_rate?: boolean }> | null | undefined): string {
  const none = noRate(rows);
  const kept = [...new Set(errors.map((e) => e.split(":")[0]))].filter((c) => !none.includes(c));
  const parts: string[] = [];
  if (kept.length) parts.push(`Couldn't read: ${kept.join(", ")} (last rate kept).`);
  if (none.length) parts.push(`No exchange rate yet for ${none.join(", ")}: ${none.length === 1 ? "it isn't" : "they aren't"} shown to visitors until one is read. Fix a price here to show one anyway.`);
  return parts.join(" ");
}
