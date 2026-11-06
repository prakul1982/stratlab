/* "Pick your broker" (owner, 5 Nov): for each broker, the ways to bring its holdings into StratLab, in this order: a live
 * connection (only where there is one), a holdings file (where to download it in that broker's app or website), and the
 * monthly depository statement by email (it covers every broker). One list, so a broker is added by adding its entry.
 *
 * File steps are only the menu names a broker's own help pages state (`help` links the page they come from). Where no page
 * of the broker's own says it, the steps stay generic ("look for Holdings, then Download / Export") rather than inventing menus.
 * The last step, uploading, is said by the guide itself: where the upload button is depends on the page (LIVE4-015: "Upload
 * the file here" on Settings, which has no upload). */

export type GuideWay = "connect" | "file" | "email";

export type GuideBroker = {
  id: string;
  name: string;
  /** the Settings connection (its route under /connect), when StratLab has a live one; "none" when one has been asked for but isn't
   * there yet: its row says so instead of leaving a person to wonder (LIVE4-015: Angel One, applied for, had no row) */
  connect?: "kite" | "upstox" | "dhan" | "none";
  file: {
    steps: string[];
    /** "known": the holdings import reads this broker's own file; "columns": read as any CSV/Excel with the columns below;
     * "pdf": the broker gives its holdings statement only as a PDF, which the import doesn't read */
    read: "known" | "columns" | "pdf";
    /** the broker's own help page the steps come from */
    help?: string;
    /** in place of the usual line on what the import makes of the file */
    note?: string;
  };
};

/** Where no page of the broker's own gives the menus (LIVE4-014): what to look for, not invented menu names. */
const generic = (where: string): string[] => [`In ${where}, look for Holdings (or Portfolio), then Download / Export.`, "Save it as CSV or Excel."];

export const GUIDE_BROKERS: GuideBroker[] = [
  { id: "zerodha", name: "Zerodha", connect: "kite", file: { read: "known", help: "https://support.zerodha.com/category/console/portfolio/articles/holding-report",
    steps: ["Log in to Console (console.zerodha.com).", "Open Portfolio, then Holdings.", "Pick the date if you want an earlier day, then press XLSX beside Download."] } },
  { id: "groww", name: "Groww", file: { read: "known", help: "https://groww.in/updates/updates-from-groww-tax-loss-harvesting-intraday-oco-bonds-and-lots-more",
    steps: ["In Groww, open your profile, then Reports.", "Choose the stocks holding statement and the date you want.", "Download it, as Excel where it's offered."] } },
  { id: "upstox", name: "Upstox", connect: "upstox", file: { read: "known", help: "https://upstox.com/help-center/248548/",
    steps: ["Log in at account.upstox.com.", "Open Reports, then Holdings.", "Pick the date, press Get Report, then Download as Excel."] } },
  { id: "angelone", name: "Angel One", connect: "none", file: { read: "known", help: "https://www.angelone.in/support/reports-and-statements/holding-statement",
    steps: ["In the Angel One app, open Portfolio.", "Pick Equity.", "Download the holdings as Excel."] } },
  { id: "dhan", name: "Dhan", connect: "dhan", file: { read: "columns", help: "https://dhan.co/support/statements-and-ledger/my-statements/how-to-view-or-download-your-holding-summary/",
    steps: ["Log in at web.dhan.co and open your profile icon.", "Open Journal by Dhan, then Statement & Reports, then Holding Summary.", "Pick the date and download it as CSV or Excel."] } },
  { id: "icici", name: "ICICI Direct", file: { read: "known", help: "https://www.icicidirect.com/faqs/stocks/how-can-i-download-a-summary-of-my-portfolio-on-website",
    steps: ["Log in on the ICICI Direct website and open Stocks.", "Open Portfolio.", "Press the Download icon and choose the file format (Excel or CSV)."] } },
  // HDFC's own help pages give no menu for a holdings file one can download (its app emails a holding statement): what to look for
  { id: "hdfc", name: "HDFC Sky / HDFC Securities", file: { read: "known", steps: generic("HDFC Sky or the HDFC Securities website"),
    note: "The import recognises the HDFC Securities holdings file as it is; any other file needs the columns Symbol (or ISIN), Quantity and Average price." } },
  { id: "kotak", name: "Kotak Neo", file: { read: "columns", help: "https://www.kotakneo.com/support/how-to-generate-the-statements-online-from-the-website-or-app",
    steps: ["In Kotak Neo, open your profile icon, then Reports.", "Choose the holdings report.", "Press the Excel icon to download it."] } },
  { id: "paytm", name: "Paytm Money", file: { read: "pdf", help: "https://www.paytmmoney.com/care/account-statements",
    steps: ["Paytm Money emails its Portfolio Holding Statement as a PDF, which can't be read here.", "Use the statement by email below, or make a CSV of your own (columns below) and upload it."] } },
  // Motilal Oswal's own help page: the Portfolio tab's download is a PDF, which the import doesn't read (like Paytm Money's)
  { id: "motilal", name: "Motilal Oswal", file: { read: "pdf", help: "https://www.motilaloswal.com/learning-centre/2021/4/how-to-download-my-demat-holdings-statement",
    steps: ["In Motilal Oswal's app or website, the Portfolio tab downloads your holdings statement as a PDF, which can't be read here.", "Use the statement by email below, or make a CSV of your own (columns below) and upload it."] } },
  { id: "other", name: "Other", file: { read: "columns", steps: generic("your broker's website or app") } },
];

export const OTHER = "other";

export function guideFor(id: string | null | undefined): GuideBroker | null {
  return GUIDE_BROKERS.find((b) => b.id === id) ?? null;
}

/** The ways a broker has, in the order they're shown: a live connection first where there is one (or where one is on its way). */
export function waysFor(b: GuideBroker): GuideWay[] {
  return [...(b.connect ? ["connect" as const] : []), "file", "email"];
}

/** What the holdings import makes of this broker's file, in a line. */
export function readLine(b: GuideBroker): string {
  if (b.file.note) return b.file.note;
  if (b.file.read === "known") return `The import recognises ${b.id === OTHER ? "the file" : `${b.name}'s file`} as it is.`;
  if (b.file.read === "pdf") return "A CSV or Excel file of your own needs the columns Symbol (or ISIN), Quantity and Average price, one stock a line.";
  return "The file needs the columns Symbol (or ISIN), Quantity and Average price, one stock a line; their names may be in any case.";
}

/** The monthly statement by email, the same for every broker. */
export const EMAIL_STEPS = [
  "NSDL or CDSL emails a statement (CAS) that lists your shares at every broker: each month you trade, every six months otherwise; CAMS or KFintech send one for mutual funds.",
  "Set up an email filter once that forwards those statements to your private StratLab address.",
  "Each statement is read when it arrives and then thrown away: only the holdings are kept.",
];

/** The filter, in one line: the senders to forward. */
export const STATEMENT_SENDERS = "nsdl.co.in OR cdslstatements.com OR camsonline.com OR kfintech.com OR mfcentral.com";

/** The holdings file's last step, said where the upload is (LIVE4-015): My Holdings has the button beside the steps; Settings links there. */
export function uploadStep(b: GuideBroker, where: "settings" | "holdings"): string | null {
  if (b.file.read === "pdf") return null;                 // its own steps already say what to do instead
  return where === "holdings" ? "Press Upload holdings file and pick the file." : "Press Upload in My Holdings and pick the file there.";
}
