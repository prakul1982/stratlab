/* IPOs (Invest → IPOs): the small pure helpers the two pages use to write dates, prices, sizes and bids. Facts and arithmetic
 * only; where the exchange has not published a date, the one SEBI's timetable gives is marked "expected". */
import { fmtDate, inr, inrCompact, money, pctPlain, price } from "./format";
import type { IpoRow, Market, Stage } from "./ipo";

/** The tabs of a market, in order: the open tab is India's only (a US offering has no public bidding window). */
export function tabsFor(m: Market): { value: Stage; label: string }[] {
  return m === "IN"
    ? [{ value: "upcoming", label: "Upcoming" }, { value: "open", label: "Open" }, { value: "closed", label: "Closed" }, { value: "listed", label: "Recently listed" }]
    : [{ value: "upcoming", label: "Upcoming" }, { value: "closed", label: "Priced" }, { value: "listed", label: "Recently listed" }];
}

/** What a tab holds, in a line under it (the Closed tab is the issues whose bidding has ended and whose shares aren't trading yet). */
export const TAB_LINE: Record<Market, Partial<Record<Stage, string>>> = {
  IN: { upcoming: "Dates announced, bidding not open yet.", open: "Open for bidding now. Each issue's closing time on its last day is the one its exchange page gives.",
    closed: "Bidding has ended; the shares are not trading yet.", listed: "Listed in the last few months." },
  US: { upcoming: "Expected to price. A US offering has no public bidding window: the price is set the evening before trading starts.",
    closed: "Priced; trading starts at the next session.", listed: "Priced and trading in the last few months." },
};

/** "17:00" is "5 PM", "19:30" is "7:30 PM" (a time the exchange's issue page gives; none is written when it does not). */
export function clockText(hm: string): string {
  const [h, m] = hm.split(":").map(Number);
  return `${h % 12 || 12}${m ? `:${String(m).padStart(2, "0")}` : ""} ${h >= 12 ? "PM" : "AM"}`;
}

/** "₹153 to ₹162", a single price when the band has none, or "–". */
export function bandText(r: Pick<IpoRow, "low" | "high" | "price" | "currency">): string {
  const dp = r.currency === "USD" ? 2 : 0;
  const p = (v: number) => price(v, r.currency, Number.isInteger(v) ? dp : 2);
  if (r.low != null && r.high != null && r.low !== r.high) return `${p(r.low)} to ${p(r.high)}`;
  const one = r.high ?? r.low ?? r.price;
  return one != null ? p(one) : "–";
}

/** "Fresh ₹500 cr + offer for sale of 1,00,00,000 shares": an issue with one part in rupees and the other in shares. */
export function partsText(p: NonNullable<IpoRow["size_parts"]>): string {
  const fresh = p.fresh_cr != null ? inrCompact(p.fresh_cr * 1e7) : p.fresh != null ? `${sharesText(p.fresh)} shares` : null;
  const ofs = p.ofs_cr != null ? inrCompact(p.ofs_cr * 1e7) : p.ofs != null ? `${sharesText(p.ofs)} shares` : null;
  return [fresh && `Fresh ${fresh}`, ofs && `${fresh ? "offer for sale of" : "Offer for sale of"} ${ofs}`].filter(Boolean).join(" + ");
}

/** The issue's size: ₹ crore in India, dollars in the US ("₹275 cr", "$150 million"). With a part in shares and no price band yet,
 *  the parts instead of the rupee part alone ("Fresh ₹500 cr + offer for sale of 1,00,00,000 shares"). */
export function sizeText(r: Pick<IpoRow, "size" | "currency" | "market"> & Partial<Pick<IpoRow, "size_parts">>): string {
  if (r.size == null && r.size_parts) return partsText(r.size_parts);
  if (r.size == null) return "–";
  if (r.market === "US") return r.size >= 1e9 ? `$${(r.size / 1e9).toLocaleString("en-US", { maximumFractionDigits: 2 })} billion` : `$${(r.size / 1e6).toLocaleString("en-US", { maximumFractionDigits: 1 })} million`;
  return inrCompact(r.size * 1e7);
}

/** "28 Oct to 30 Oct 2026" (the year only at the end), "28 Oct 2026" for one day. */
export function spanText(a?: string | null, b?: string | null): string {
  if (a && b && a !== b) return `${fmtDate(a, { year: false })} to ${fmtDate(b)}`;
  return fmtDate(a ?? b ?? null);
}

/** A date with "expected" after it when it is the one SEBI's timetable gives, not the exchange's own. */
export const expectedText = (d: string | null | undefined, expected?: boolean) => (d ? `${fmtDate(d)}${expected ? " (expected)" : ""}` : "Not published yet");

/** "46.06 times" / "5.9 times": how many times the shares offered the bids came to. */
export function timesText(t: number | null | undefined): string {
  if (t == null) return "–";
  return `${t >= 100 ? Math.round(t).toLocaleString("en-IN") : t.toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: t < 10 ? 2 : 1 })} times`;
}

/** A change against the issue price: "+9.2% on ₹586" (the sign stays in the text). */
export function againstIssue(pctValue: number | null | undefined, r: Pick<IpoRow, "price" | "currency">): string {
  if (pctValue == null) return "–";
  return `${pctValue > 0 ? "+" : pctValue < 0 ? "−" : ""}${pctPlain(Math.abs(pctValue), 1)}${r.price != null ? ` on ${price(r.price, r.currency, 2)}` : ""}`;
}

/** Rupees or dollars of a lot at a price: "₹14,742". */
export const minText = (r: Pick<IpoRow, "min_amount" | "currency">) => (r.min_amount != null ? (r.currency === "USD" ? money(r.min_amount, "USD", 2) : inr(r.min_amount)) : "–");

/** A number of shares with its market's grouping. */
export const sharesText = (n: number | null | undefined, market: Market = "IN") => (n == null ? "–" : n.toLocaleString(market === "IN" ? "en-IN" : "en-US"));

/** ₹ crore as the offer document gives it. */
export const croreText = (v: number | null | undefined) => (v == null ? "–" : inrCompact(v * 1e7));

export const STAGE_BADGE: Record<Stage, { word: string; tone: "ok" | "warn" | "plain" | "live" }> = {
  filed: { word: "Filed, no dates yet", tone: "plain" }, upcoming: { word: "Upcoming", tone: "ok" }, open: { word: "Open for bidding", tone: "live" },
  closed: { word: "Closed, not listed yet", tone: "plain" }, listed: { word: "Listed", tone: "plain" },
  withdrawn: { word: "Withdrawn", tone: "warn" }, social: { word: "Social Stock Exchange raise, not an IPO", tone: "plain" },
};

/** What the exchange says happened to an issue that did not go ahead: "Withdrawn", "Postponed" or "Cancelled". */
export const STATUS_WORD: Record<NonNullable<IpoRow["issue_status"]>, string> = { withdrawn: "Withdrawn", postponed: "Postponed", cancelled: "Cancelled" };

/** The badge of an issue: its stage's, but an issue that did not go ahead says which way (withdrawn, postponed or cancelled). */
export function badgeOf(r: Pick<IpoRow, "stage" | "issue_status">) {
  return r.stage === "withdrawn" && r.issue_status ? { ...STAGE_BADGE.withdrawn, word: STATUS_WORD[r.issue_status] } : STAGE_BADGE[r.stage];
}

export const segmentWord = (r: Pick<IpoRow, "segment" | "market">) => (r.market === "US" ? "" : r.segment === "sme" ? "SME" : r.segment === "mainboard" ? "Mainboard" : "");
