/** The companies named in the filings feed's `problems` ("TCS: The exchange feed isn't answering right now…"), each once. */
export function unreadSymbols(problems: string[] | null | undefined): string[] {
  const out: string[] = [];
  for (const p of problems ?? []) {
    const sym = p.split(":")[0].trim();
    if (sym && !out.includes(sym)) out.push(sym);
  }
  return out;
}

/** What to say when the filings of some companies couldn't be read: "Couldn't read TCS's filings right now." for one,
 * "Couldn't read the filings of TCS and INFY right now." for two or three, "… of TCS, INFY, ITC and 2 more …" beyond that.
 * Never says there are no stocks: the feed failing is not the same as nothing to show (R13S-002). */
export function unreadLine(symbols: string[]): string {
  const n = symbols.length;
  if (n === 0) return "Couldn't read your companies' filings right now.";
  if (n === 1) return `Couldn't read ${symbols[0]}'s filings right now.`;
  const names = n <= 3 ? `${symbols.slice(0, -1).join(", ")} and ${symbols[n - 1]}` : `${symbols.slice(0, 3).join(", ")} and ${n - 3} more`;
  return `Couldn't read the filings of ${names} right now.`;
}
