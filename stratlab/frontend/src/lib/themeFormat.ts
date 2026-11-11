import { CRORE, bigMoney, pctPlain } from "./format";
import type { Region } from "./research";
import type { DiveRow, Layer, Stat } from "./theme";

/** An amount in the dive's unit ("₹ crore" or "$ million") as the app writes money: ₹1.51 lakh cr, $2.4B. The one rule for big money
 * (bigMoney), as the company page, its public page, the screens and Compare write a market value (LIVE3-018: "₹11.4 lakh cr" here
 * beside "₹11.38 lakh cr" there). */
export function amount(v: number | null | undefined, region: Region): string {
  if (v == null || !Number.isFinite(v)) return "–";
  return bigMoney(region === "IN" ? v * CRORE : v * 1e6, region === "IN" ? "INR" : "USD");
}
/** A margin or rate in percent, one decimal, the real minus. */
export const pc = (v: number | null | undefined, dp = 1) => pctPlain(v, dp).replace("-", "−");
/** A multiple: 12.4x. */
export const times = (v: number | null | undefined, dp = 1) => (v == null || !Number.isFinite(v) ? "–" : `${v.toFixed(dp)}x`);
/** A change in percentage points: +2.0 pts, −0.5 pts. */
export const points = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)} pts`);
/** "48.0% to 50.0%" for a range; one value when they are the same. */
export const span = (s: Stat | null | undefined, f: (v: number) => string = (v) => pc(v)) => (!s ? "–" : s.min === s.max ? f(s.min) : `${f(s.min)} to ${f(s.max)}`);

/** A median is shown only on MIN_BASE companies or more (the deck's rule, R20: "median of 2" is two values, shown as they are on their rows). */
export const MIN_BASE = 3;
/** Why a listed company is left out of its layer's calculations, in words (the deck's notes; theme_data.CALC_WHY). */
export const CALC_WORDS: Record<string, string> = {
  "other business": "it earns another way than most of this layer's companies",
  "way of earning not shown": "its evidence doesn't show clearly how it earns",
  "not confirmed": "its own words don't show this work",
  "no revenue figure": "no revenue figure is stored for it",
};
/** A company row's place in its layer's calculations, as the server kept it (theme_data.calc_record); a row kept without one is in. */
export const calcOf = (row: DiveRow): { in: boolean; why: string } => (row.calc && typeof row.calc.in === "boolean" ? row.calc : { in: true, why: "" });

/** A median cell as the deck writes it (deck._medn): "–" when no company has the figure; "–" with "(2 of 6)" when fewer than MIN_BASE
 *  do; the median, with "(5 of 6)" when it is of fewer companies than the `of` in the layer's calculations. */
export function medCell(s: Stat | null | undefined, of: number, f: (v: number) => string = (v) => pc(v)): { text: string; base: string } {
  if (!s || !s.n) return { text: "–", base: "" };
  const base = of && s.n < of ? `${s.n} of ${of}` : "";
  if (s.n < MIN_BASE) return { text: "–", base: base || `${s.n}` };
  return { text: f(s.median), base };
}

/** The table of one layer: its companies, each left-out one marked with why (LIVE6-001), then the layer's median of the companies in its
 *  calculations and the range, as the last two rows; a range only where a median is shown. */
export interface LayerLine { kind: "company" | "median" | "range"; key: string; row?: DiveRow; label?: string; stats?: Layer["stats"]; of?: number }
export function layerLines(l: Layer): LayerLine[] {
  const out: LayerLine[] = l.companies.map((row) => ({ kind: "company", key: row.symbol, row }));
  if (l.companies.length > 0) {
    const n = l.n ?? l.companies.filter((c) => calcOf(c).in).length;
    out.push({ kind: "median", key: "~median", stats: l.stats, of: n,
      label: `Median of the ${n} in the layer's calculations${l.stats_over === "all" ? " (company-wide figures)" : ""}` });
    const shown = (["ebitda", "net", "roce"] as const).some((k) => (l.stats[k]?.n ?? 0) >= MIN_BASE);
    if (shown) out.push({ kind: "range", key: "~range", stats: l.stats, label: "Range", of: n });
  }
  return out;
}

/* LIVE6-007: a line is shown as a company's own words only when it says what the company does (theme_base.own_words, the same rule for the
 * page, the CSV and the deck): never a filing's title ("From its own filings: Annual report (20-F)"), its name alone, or an encyclopedia
 * lead that says where it is but not what it does. */
export const NO_WORDS = "No description in its own words yet";
const WORK = /\b(?:provid\w*|produc(?:es|ers?|ing|ts?|tion)|manufactur\w*|makes?|making|makers?|sells?|selling|suppl(?:y|ies|ying|iers?)|designs?|designing|develop(?:s|ing|ers?)|operat(?:es|ing|ors?)|offers?|offering|distribut\w*|retail\w*|services?|servic(?:es|ing)|foundr(?:y|ies)|licens\w*|leases?|leasing|lend(?:s|ing|ers?)|insur\w*|earns?|revenues?|customers?|clients?|subscri\w*|platforms?|stores?|brands?|engag(?:ed|es)|build(?:s|ing|ers?)|construct\w*|mines?|mining|miners?|refin\w*|generat(?:es|ing|ors?)|transmi\w*|explor(?:es|ing|ation)|invest(?:s|ing|ments?)|manag(?:es|ing)|deliver\w*|software|hardware|solutions?|products?|systems?|equipment|devices?|vehicles?|drugs?|medicines?|banking|bank|loans?|chemicals?|steel|cement|power|electricity|specializ\w*|specialis\w*|focus(?:es|ed) on|helps?|enables?|protect\w*|secur(?:es|ing))\b/i;
const FILING_TITLE = /^(?:annual|quarterly|current|interim|half[- ]yearly)\s+report\b|^(?:form\s+)?(?:10-[kq]|20-f|40-f|8-k|6-k|def\s*14a)\b|^(?:press release|investor presentation|board meeting|outcome of board meeting|shareholding pattern|financial results)\b/i;
const LEGAL_WORDS = /\b(?:inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|lp|nv|sa|ag|the|holdings?|group)\b\.?/gi;
const wordsOf = (x: string) => x.toLowerCase().replace(LEGAL_WORDS, " ").match(/[a-z0-9]+/g) ?? [];
export function ownWords(text: string | null | undefined, name = ""): string {
  const t = (text ?? "").split(/\s+/).filter(Boolean).join(" ").replace(/^[\s“”"']+|[\s“”"']+$/g, "");
  if (!t || t.startsWith("From its own filings:") || FILING_TITLE.test(t)) return "";
  if (name) { const have = new Set(wordsOf(name)); if (!wordsOf(t).some((w) => !have.has(w))) return ""; }
  return WORK.test(t) ? t : "";
}
