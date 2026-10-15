/* Why the trade journal's numbers differ from the tax report's, from the same trades (R7M-013: "11 closed trades, +₹34 after
 * charges" beside "19 sale lines, −₹59" and ₹2.13 crore of F&O the journal does not show). Facts about how each is counted. */

/** The journal's promise about what it covers, under the page title. */
export const JOURNAL_LEDE = "Your broker's trades as round trips after charges, checked like a backtest: equity from a tradebook or your tax report, "
  + "F&O, commodity and currency from a tradebook or the tax P&L's trade-by-trade files, and US stocks and crypto you add by hand. Only you can see them.";

/** The paragraphs of "Why these numbers differ from your tax report". `fno`: the tax report holds F&O, commodity or currency
 * totals that the journal's stats do not count. */
export function journalVsTax(fno: boolean): string[] {
  return [
    "The journal follows each position from flat to flat: a round trip opens with the first purchase (or sale, for a short) and closes "
      + "when the position is back to nothing, at the average price of its purchases and of its sales, and it counts one round trip per position closed. "
      + "The tax report lists every sale line on its own, matches tradebook sales to the oldest purchases first, and files each one as short-term or long-term. "
      + "A share bought in three lots and sold in two pieces is one round trip here and several sale lines there, so the counts differ before any rupee does.",
    "The journal's headline is the profit or loss of those round trips after charges, with the figure before charges beside it. "
      + "Where your files list the charges, the journal takes off the same rupees as the tax report: on sale lines from the tax report, and on "
      + "tradebook trades whose file has charges or STT columns, the charges as listed, plus STT on shares bought and sold the same day (intraday, "
      + "where the tax report deducts it; it doesn't deduct STT from capital gains). A sale line that a tradebook also has is counted once, the way the tax report counts it. "
      + "Tradebook trades whose file has neither charges nor STT columns are charged here at the published rates, STT included, while the tax report takes off none for them: "
      + "on those trades the two figures differ by those charges. Without trade times, shares bought and sold on a day you already held some stay "
      + "part of the open position here, while the tax report books the matched part as intraday.",
    fno
      ? "F&O, commodity and currency trades are business income in the tax report, which keeps them as one total for each financial year "
        + "(the card below the trades). They are not round trips in this journal's stats. Upload the tax P&L's trade-by-trade files to count them here."
      : "F&O, commodity and currency trades are business income in the tax report, which keeps them as one total for each financial year. "
        + "They are in this journal only when they come from a tradebook or the tax P&L's trade-by-trade files.",
  ];
}

/** The journal's date line. Its date is when the journal last changed (an import, a note, a hidden or added trade); the tax
 * report's "updated" date is when its own files last changed, so the two can differ for the same import (R28-013). */
export const journalSavedNote = (asOf: string, updatedAt: string | null, fmt: (iso: string) => string): string =>
  `Worked out as of ${fmt(asOf)}${updatedAt ? ` · journal last changed ${fmt(updatedAt)} (the tax report has its own date, from its last file)` : ""}.`;
