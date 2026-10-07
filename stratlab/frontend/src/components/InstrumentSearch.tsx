import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import type { Instrument, Market } from "../lib/types";
import { useSurveillance } from "../lib/surveillance";
import { Search } from "./Icons";
import { SurvBadges } from "./Surveillance";
import "../pages/trade/trade.css";

let defaultsCache: Instrument[] | null = null;

function useDefaults(): Instrument[] {
  const [d, setD] = useState<Instrument[]>(defaultsCache ?? []);
  useEffect(() => {
    if (defaultsCache) return;
    api<Instrument[]>("/instruments/defaults").then((x) => { defaultsCache = x; setD(x); }).catch(() => {});
  }, []);
  return d;
}

/** The Indian symbols the person holds (My Holdings), read once a page: the picks a picker offers first. */
let heldCache: Promise<string[]> | null = null;
function useHeld(on: boolean): string[] {
  const [held, setHeld] = useState<string[]>([]);
  useEffect(() => {
    if (!on) return;
    heldCache ??= api<{ rows?: { symbol: string; market?: string; kind?: string }[] }>("/holdings")
      .then((h) => (h.rows ?? []).filter((r) => (r.market ?? "IN") === "IN").map((r) => r.symbol)).catch(() => []);
    let live = true;
    heldCache.then((s) => { if (live) setHeld(s); });
    return () => { live = false; };
  }, [on]);
  return held;
}

const instKind = (r: Instrument) =>
  r.market === "MCX" ? `MCX futures · ${r.contract ?? ""}`.trim() : r.market === "CDS" ? `Currency futures · ${r.contract ?? ""}`.trim() : r.market === "CMDTY" ? "Futures, front month"
    : r.type === "EQ" ? "Stock" : r.type === "INDEX" ? "Index" : r.type === "ETF" ? "ETF" : r.type === "FX" ? "Currency pair"
    : r.type === "CRYPTO" ? r.currency : `${r.type}${r.expiry ? " " + r.expiry : ""}`;

const PLACEHOLDER: Record<string, string> = {
  IN: "Search a stock, index or F&O: RELIANCE, NIFTY 50", CRYPTO: "Search a coin: BTC, ETH, SOL",
  US: "Search a US stock or ETF: AAPL, NVDA", UK: "Search a London listing: Shell, VOD.L",
  EU: "Search a European stock: SAP, ASML", JP: "Search a Tokyo listing: Toyota, Sony",
  FX: "Search a currency pair: EURUSD, USDJPY",
  MCX: "Search MCX: gold mini, crude oil, copper",
  CDS: "Search currency futures: USDINR, EURINR",
  CMDTY: "Search commodities: gold, WTI crude, Brent",
};

/** Search box plus popular picks for one market, with the same keys as every other suggestion box (StockPicker): up and
 * down move, Enter picks, Esc closes. `kinds` keeps only some instrument types (a SIP takes stocks and ETFs, "EQ" and
 * "ETF"; Indian ETFs trade as "EQ"), in the suggestions and the quick picks alike, and `placeholder` says what fits.
 * The quick picks are the person's own holdings first, then the market's popular ones. */
export function InstrumentSearch({ market, onPick, autoFocus, compact, kinds, placeholder, label }: {
  market: Market; onPick: (i: Instrument) => void; autoFocus?: boolean; compact?: boolean;
  kinds?: string[]; placeholder?: string; label?: string;
}) {
  const { fail } = useApp();
  const fid = useId();
  const listId = `${fid}-list`;
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Instrument[] | null>(null);
  const [on, setOn] = useState(-1);
  const [open, setOpen] = useState(false);
  const timer = useRef<number>(undefined);
  const asked = useRef(0);
  const fits = (i: Instrument) => !kinds || kinds.includes(i.type ?? "");
  const defaults = useDefaults().filter((d) => d.market === market.id && fits(d));
  const held = useHeld(market.id === "IN").filter((s) => !defaults.some((d) => d.symbol === s)).slice(0, 4);
  const surv = useSurveillance(market.id === "IN");

  useEffect(() => { setQ(""); setResults(null); }, [market.id]);
  useEffect(() => {
    window.clearTimeout(timer.current);
    if (q.trim().length < 2) { setResults(null); setOn(-1); return; }
    const n = ++asked.current;
    timer.current = window.setTimeout(async () => {
      try {
        const got = (await api<Instrument[]>(`/instruments/search?q=${encodeURIComponent(q.trim())}&market=${market.id}`)).filter(fits);
        if (n === asked.current) { setResults(got); setOn(got.length ? 0 : -1); setOpen(true); }
      } catch (e) { fail(e); }
    }, 250);
  }, [q, market.id, fail]);   // eslint-disable-line react-hooks/exhaustive-deps

  const pick = (i: Instrument) => { asked.current++; setQ(""); setResults(null); setOn(-1); setOpen(false); onPick(i); };
  /** A held symbol from the quick picks: found by its exact symbol first, so it carries the market's own instrument. */
  const pickHeld = async (sym: string) => {
    try {
      const got = (await api<Instrument[]>(`/instruments/search?q=${encodeURIComponent(sym)}&market=${market.id}`)).filter(fits);
      const hit = got.find((i) => i.symbol === sym);
      if (hit) pick(hit); else setQ(sym);
    } catch (e) { fail(e); }
  };
  const key = (e: KeyboardEvent<HTMLInputElement>) => {
    const rows = results ?? [];
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setOn((a) => (rows.length ? (a + 1) % rows.length : -1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setOn((a) => (rows.length ? (a <= 0 ? rows.length - 1 : a - 1) : -1)); }
    else if (e.key === "Enter") { if (open && rows[on]) { e.preventDefault(); pick(rows[on]); } else if (rows.length) e.preventDefault(); }
    else if (e.key === "Escape") { if (open && rows.length) { e.preventDefault(); e.stopPropagation(); setOpen(false); } else setQ(""); }
  };
  const shown = open && !!results;
  const what = kinds ? kinds.map((k) => (k === "EQ" ? "stocks" : k === "ETF" ? "ETFs" : k === "INDEX" ? "indices" : k)).filter((x, i, a) => a.indexOf(x) === i).join(" and ") : null;

  return (
    <div className="k-stack">
      <div className={`search-box${compact ? " compact" : ""}`}>
        <Search />
        <input id={fid} autoFocus={autoFocus} value={q} autoComplete="off" spellCheck={false} aria-label={label ?? `Search ${market.name}`}
          role="combobox" aria-expanded={shown} aria-controls={listId} aria-autocomplete="list" aria-activedescendant={shown && on >= 0 ? `${fid}-o${on}` : undefined}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }} onKeyDown={key}
          onFocus={() => { if (results) setOpen(true); }} onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          placeholder={placeholder ?? PLACEHOLDER[market.id] ?? "Search by name or symbol"} />
        {shown && (
          <div className="results" id={listId} role="listbox" aria-label="Suggestions">
            {results!.length === 0 && <p className="k-small k-muted k-pad" role="presentation">No {what ?? "matches"} in {market.name} {what ? "match" : ""} "{q.trim()}".</p>}
            {results!.map((r, i) => (
              <button key={r.id} id={`${fid}-o${i}`} type="button" role="option" aria-selected={i === on} className={i === on ? "on" : undefined}
                onMouseDown={(e) => e.preventDefault()} onMouseMove={() => setOn(i)} onClick={() => pick(r)}>
                <span><b>{r.symbol}</b> <span className="small muted">{r.name !== r.symbol ? r.name : ""}</span>
                  {market.id === "IN" && <> <SurvBadges region="IN" symbol={r.symbol} plain /></>}</span>
                <span className="small muted">{instKind(r)}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      {(held.length > 0 || defaults.length > 0) && (
        <div className="k-row">
          {held.length > 0 && <>
            <span className="k-small k-muted">Yours:</span>
            {held.map((s) => <button key={`h-${s}`} type="button" className="btn quiet sm" onClick={() => void pickHeld(s)}>{s}</button>)}
          </>}
          {defaults.length > 0 && <>
            <span className="k-small k-muted">Popular:</span>
            {defaults.map((d) => <button key={d.id} type="button" className="btn quiet sm" onClick={() => pick(d)}>{d.symbol}
              {market.id === "IN" && <> <SurvBadges region="IN" symbol={d.symbol} plain /></>}</button>)}
          </>}
        </div>
      )}
      {surv && [...(results ?? []), ...defaults].some((i) => surv.flags[i.symbol]) && <p className="k-note">Small tags such as LT-ASM 2, T2T or F&amp;O ban are the exchange's
        surveillance lists today; a stock's company page explains each.</p>}
    </div>
  );
}
