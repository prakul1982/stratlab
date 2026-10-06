import { useEffect, useRef, useState } from "react";
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

/** Search box plus popular picks for one market. */
export function InstrumentSearch({ market, onPick, autoFocus, compact }: {
  market: Market; onPick: (i: Instrument) => void; autoFocus?: boolean; compact?: boolean;
}) {
  const { fail } = useApp();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Instrument[] | null>(null);
  const timer = useRef<number>(undefined);
  const defaults = useDefaults().filter((d) => d.market === market.id);
  const surv = useSurveillance(market.id === "IN");

  useEffect(() => { setQ(""); setResults(null); }, [market.id]);
  useEffect(() => {
    window.clearTimeout(timer.current);
    if (q.trim().length < 2) { setResults(null); return; }
    timer.current = window.setTimeout(async () => {
      try { setResults(await api<Instrument[]>(`/instruments/search?q=${encodeURIComponent(q.trim())}&market=${market.id}`)); }
      catch (e) { fail(e); }
    }, 250);
  }, [q, market.id, fail]);

  const pick = (i: Instrument) => { setQ(""); setResults(null); onPick(i); };

  return (
    <div className="k-stack">
      <label className={`search-box${compact ? " compact" : ""}`}>
        <Search />
        <span className="sr-only">Search {market.name}</span>
        <input autoFocus={autoFocus} value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Escape") setQ(""); }}
          placeholder={PLACEHOLDER[market.id] ?? "Search by name or symbol"} />
        {results && (
          <div className="results">
            {results.length === 0 && <p className="k-small k-muted k-pad">No matches in {market.name}.</p>}
            {results.map((r) => (
              <button key={r.id} type="button" onClick={() => pick(r)}>
                <span><b>{r.symbol}</b> <span className="small muted">{r.name !== r.symbol ? r.name : ""}</span>
                  {market.id === "IN" && <> <SurvBadges region="IN" symbol={r.symbol} plain /></>}</span>
                <span className="small muted">{instKind(r)}</span>
              </button>
            ))}
          </div>
        )}
      </label>
      {defaults.length > 0 && (
        <div className="k-row">
          <span className="k-small k-muted">Popular:</span>
          {defaults.map((d) => <button key={d.id} type="button" className="btn quiet sm" onClick={() => pick(d)}>{d.symbol}
            {market.id === "IN" && <> <SurvBadges region="IN" symbol={d.symbol} plain /></>}</button>)}
        </div>
      )}
      {surv && [...(results ?? []), ...defaults].some((i) => surv.flags[i.symbol]) && <p className="k-note">Small tags such as LT-ASM 2, T2T or F&amp;O ban are the exchange's
        surveillance lists today; a stock's company page explains each.</p>}
    </div>
  );
}
