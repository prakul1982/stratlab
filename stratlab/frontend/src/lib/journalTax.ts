/* Why the trade journal's numbers differ from the tax report's, from the same trades (R7M-013: "11 closed trades, +₹34 after
 * charges" beside "19 sale lines, −₹59" and ₹2.13 crore of F&O the journal does not show). Facts about how each is counted. */

/** The journal's promise about what it covers, under the page title. */
export const JOURNAL_LEDE = "Your broker's trades as round trips after charges, checked like a backtest: equity from a tradebook or your tax report, "
  + "F&O, commodity and currency from a tradebook or the tax P&L's trade-by-trade files, and US stocks and crypto you add by hand. Only you can see them.";

/** The paragraphs of "Why these numbers differ from your tax report". `fno`: the tax report holds F&O, commodity or currency
 * totals that the journal's stats do not count. */
export function journalVsTax(fno: boolean): string[] {
  return [
    "The journal pairs each purchase with the sales that close it, first in, first out, and counts one round trip per position closed. "
      + "The tax report lists every sale line on its own and files each one as short-term or long-term. A share bought in three lots "
      + "and sold in two pieces is one round trip here and several sale lines there, so the counts differ before any rupee does.",
    "The journal's headline is the profit or loss of those round trips after the charges it works out for each trade, with the figure "
      + "before charges beside it. The tax report totals gains and losses by its own rules for each sale line, so the two are not the same sum. "
      + "Sale lines that came from the tax report keep its sale values and the charges its file lists, so on those lines the journal's net after charges "
      + "and the tax report's gain are the same rupees; trades from a tradebook are charged at the published rates.",
    fno
      ? "F&O, commodity and currency trades are business income in the tax report, which keeps them as one total for each financial year "
        + "(the card below the trades). They are not round trips in this journal's stats. Upload the tax P&L's trade-by-trade files to count them here."
      : "F&O, commodity and currency trades are business income in the tax report, which keeps them as one total for each financial year. "
        + "They are in this journal only when they come from a tradebook or the tax P&L's trade-by-trade files.",
  ];
}
