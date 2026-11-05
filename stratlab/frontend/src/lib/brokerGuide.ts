/* "Pick your broker" (owner, 5 Nov): for each broker, the ways to bring its holdings into StratLab, in this order: a live
 * connection (only where there is one), a holdings file (where to download it in that broker's app or website), and the
 * monthly depository statement by email (it covers every broker). One list, so a broker is added by adding its entry.
 *
 * File steps are only the menu names a broker's own help pages state (`help` links the page they come from). Where no page
 * of the broker's own says it, the steps stay generic ("Holdings, then Download or Export") rather than inventing menus. */

export type GuideWay = "connect" | "file" | "email";

export type GuideBroker = {
  id: string;
  name: string;
  /** the Settings connection (its route under /connect), when StratLab has a live one */
  connect?: "kite" | "upstox" | "dhan";
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

const GENERIC = ["Open your holdings (or portfolio) in the broker's website or app.", "Use its Download or Export button, as CSV or Excel.", "Upload the file here."];

export const GUIDE_BROKERS: GuideBroker[] = [
  { id: "zerodha", name: "Zerodha", connect: "kite", file: { read: "known", help: "https://support.zerodha.com/category/console/portfolio/articles/holding-report",
    steps: ["Log in to Console (console.zerodha.com).", "Open Portfolio, then Holdings.", "Pick the date if you want an earlier day, then press XLSX beside Download.", "Upload the file here."] } },
  { id: "groww", name: "Groww", file: { read: "known", help: "https://groww.in/updates/updates-from-groww-tax-loss-harvesting-intraday-oco-bonds-and-lots-more",
    steps: ["In Groww, open your profile, then Reports.", "Choose the stocks holding statement and the date you want.", "Download it (Excel where it's offered) and upload the file here."] } },
  { id: "upstox", name: "Upstox", connect: "upstox", file: { read: "known", help: "https://upstox.com/help-center/248548/",
    steps: ["Log in at account.upstox.com.", "Open Reports, then Holdings.", "Pick the date, press Get Report, then Download as Excel.", "Upload the file here."] } },
  { id: "angelone", name: "Angel One", file: { read: "known", help: "https://www.angelone.in/support/reports-and-statements/holding-statement",
    steps: ["In the Angel One app, open Portfolio.", "Pick Equity.", "Download the holdings as Excel.", "Upload the file here."] } },
  { id: "dhan", name: "Dhan", connect: "dhan", file: { read: "columns", help: "https://dhan.co/support/statements-and-ledger/my-statements/how-to-view-or-download-your-holding-summary/",
    steps: ["Log in at web.dhan.co and open your profile icon.", "Open Journal by Dhan, then Statement & Reports, then Holding Summary.", "Pick the date and download it as CSV or Excel.", "Upload the file here."] } },
  { id: "icici", name: "ICICI Direct", file: { read: "known", steps: GENERIC } },
  { id: "hdfc", name: "HDFC Sky / HDFC Securities", file: { read: "known", steps: GENERIC,
    note: "The import recognises the HDFC Securities holdings file as it is; any other file needs the columns Symbol (or ISIN), Quantity and Average price." } },
  { id: "kotak", name: "Kotak Neo", file: { read: "columns", help: "https://www.kotakneo.com/support/how-to-generate-the-statements-online-from-the-website-or-app",
    steps: ["In Kotak Neo, open your profile icon, then Reports.", "Choose the holdings report.", "Press the Excel icon to download it.", "Upload the file here."] } },
  { id: "paytm", name: "Paytm Money", file: { read: "pdf", help: "https://www.paytmmoney.com/care/account-statements",
    steps: ["Paytm Money emails its Portfolio Holding Statement as a PDF, which can't be read here.", "Use the monthly statement by email below, or make a CSV of your own (columns below) and upload it."] } },
  { id: "motilal", name: "Motilal Oswal", file: { read: "columns", steps: GENERIC } },
  { id: "other", name: "Other", file: { read: "columns", steps: GENERIC } },
];

export const OTHER = "other";

export function guideFor(id: string | null | undefined): GuideBroker | null {
  return GUIDE_BROKERS.find((b) => b.id === id) ?? null;
}

/** The ways a broker has, in the order they're shown: a live connection first where there is one. */
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
  "NSDL or CDSL emails a monthly statement that lists your shares at every broker; CAMS or KFintech send one for mutual funds.",
  "Set up an email filter once that forwards those statements to your private StratLab address.",
  "Each statement is read when it arrives and then thrown away: only the holdings are kept.",
];

/** The filter, in one line: the senders to forward. */
export const STATEMENT_SENDERS = "nsdl.co.in OR cdslstatements.com OR camsonline.com OR kfintech.com OR mfcentral.com";
