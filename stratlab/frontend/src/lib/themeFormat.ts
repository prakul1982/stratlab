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
/** An EBITDA margin as precise as it is filed (LIVE7A-009, deck._pcw): whole points print as 12%, never 12.0%; a median's half stays (16.5%). */
export const pcw = (v: number | null | undefined, whole: boolean) => (whole ? pc(v).replace(/\.0%$/, "%") : pc(v));
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
  // LIVE7A-011: the largest company first, as the deck's layer tables are (a company with no market value last, in the order given)
  const byCap = [...l.companies].sort((a, b) => (b.cap ?? -Infinity) - (a.cap ?? -Infinity) || 0);
  const out: LayerLine[] = byCap.map((row) => ({ kind: "company", key: row.symbol, row }));
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
/* LIVE7A-004: an encyclopedia's opening line ("is an American ...", "commonly known as"), a line that only adds to an earlier one ("We also
 * offer ...") or only says where the company is ("It is headquartered in ...") is not its own words (theme_base._ENCYCLOPEDIA, _ADDS, _WHERE). */
const ENCYCLOPEDIA = /^[^.]{0,160}?\b(?:is|was)\s+(?:an?|the)\s+(?:[\w&'-]+,?\s+){0,3}?(?:American|British|English|Scottish|Japanese|Taiwanese|(?:South\s+)?Korean|Chinese|Indian|Israeli|Dutch|German|French|Swiss|Canadian|Irish|Swedish|Finnish|Norwegian|Danish|Italian|Spanish|Belgian|Australian|Singaporean|Brazilian|Mexican|Argentine|Bermudian|Luxembourgish|Greek|Cypriot|multinational|publicly[\s-]traded)\b|^[^.]{0,80}?,\s+(?:commonly|also|formerly|better)\s+known\s+as\b/i;
const ABBR_DOT = /\b(inc|corp|co|ltd|plc|l\.p|n\.v|s\.a|bhd|pty|ltda|st)\./gi;
const ADDS = /^(?:in\s+addition\b|additionally\b|also\b|(?:we|it|they|the\s+company)\s+also\b)/i;
const WHERE = /^(?:it|we|the\s+company)\s+(?:is|are)\s+(?:headquartered|based|located|domiciled|incorporated)\b/i;
export function ownWords(text: string | null | undefined, name = ""): string {
  const t = (text ?? "").split(/\s+/).filter(Boolean).join(" ").replace(/^[\s“”"']+|[\s“”"']+$/g, "");
  if (!t || t.startsWith("From its own filings:") || FILING_TITLE.test(t) || ENCYCLOPEDIA.test(t.replace(ABBR_DOT, "$1")) || ADDS.test(t) || WHERE.test(t)) return "";
  if (name) { const have = new Set(wordsOf(name)); if (!wordsOf(t).some((w) => !have.has(w))) return ""; }
  return WORK.test(t) ? t : "";
}

/** The heading of the search box's list of themes StratLab has already mapped (LIVE6-012). It is one shared library, kept once for
 *  everyone, not this person's reading history: it never says "Already read" or "read <date>" (an account that never opened a theme was
 *  shown "Already read: Cybersecurity · US, read 11 Nov"); the date is when the stored map was last updated. */
export const LIBRARY_HEAD = "Ready to open:";
export function libraryLabel(i: { name: string; region: string; at: string | null; day?: string | null }, fmtDay: (iso: string) => string): string {
  const where = ({ IN: "India", US: "US" } as Record<string, string>)[i.region] ?? i.region;
  // LIVE7A-008: the map's own day in the market's time zone, the date its page says "Last updated" (theme_library.updated_at)
  const day = i.day ?? (i.at ? i.at.slice(0, 10) : null);
  return `${i.name} · ${where}${day ? `, updated ${fmtDay(day)}` : ""}`;
}

/** A layer's operating figures by its own companies, never by its place in the list (LIVE7A-005: the map's layers and the page's are not the
 *  same list, so the two-wheeler makers' table sat under the next layer). Rows in the layer's company order; undefined before they're read. */
export function bizFor<R extends { symbol: string }>(biz: { layers: { layer: string; rows: R[] }[] } | null | undefined, layer: { companies: { symbol: string }[] }): R[] | undefined {
  if (!biz) return undefined;
  const by = new Map<string, R>();
  for (const g of biz.layers) for (const r of g.rows) if (!by.has(r.symbol)) by.set(r.symbol, r);
  return layer.companies.map((c) => by.get(c.symbol)).filter((r): r is R => !!r);
}

/* LIVE7A-011: the SEC's industry title worded for a reader, as the company pages word it (stock_pages.plain_industry): "Radio & Tv Broadcasting &
 * Communications Equipment" as "Radio and TV broadcasting and communications equipment", without a "Services-" prefix or the catch-all "Nec".
 * A name that isn't in title case (an Indian industry's) is left as it is. */
const SIC_ACRONYMS: Record<string, string> = { tv: "TV", us: "US", hmos: "HMOs", reits: "REITs", reit: "REIT", ii: "II", iii: "III", ev: "EV" };
export function plainIndustry(text: string | null | undefined): string {
  const t = (text ?? "").trim();
  const title = t.replace(/\b([a-z])([a-z]*)/gi, (_, a: string, b: string) => a.toUpperCase() + b.toLowerCase());
  if (!t || t !== title) return t;
  const core = t.replace(/^(?:services|retail|wholesale)\s*-\s*/i, "").replace(/[,\s]*\(?\b(?:nec|not elsewhere classified)\b\)?\s*$/i, "").replace(/^[\s,-]+|[\s,-]+$/g, "") || t;
  const out = core.replace(/ & /g, " and ").split(" ").map((w) => SIC_ACRONYMS[w.toLowerCase().replace(/[(),]/g, "")] ?? w.toLowerCase()).join(" ");
  return out.slice(0, 1).toUpperCase() + out.slice(1);
}
