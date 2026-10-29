import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Card, EmptyState, PageHeader, Select } from "../components/kit";
import { ChartWorkspace } from "../components/watch/ChartWorkspace";
import { openMarkets } from "../components/watch/Launcher";
import { useApp } from "../lib/app";
import { currencySymbol, signCls } from "../lib/format";
import { useDocTitle } from "../lib/title";
import { live, putItems } from "../lib/watchApi";
import { changeOf, changeText, currencyOf, itemFromPath, labelOf, MARKET_NAME, priceText, subtitleOf, type WatchQuote } from "../lib/watch";
import { useWatch } from "../components/watch/useWatch";
import "./chart.css";

/* /chart/<market>/<symbol>: one instrument's chart as a page (MW-1). The same chart as in the Market Watch panel: every timeframe
 * from 1 minute to 1 month, drawings, indicators and the timeframe kept on the account for this symbol, and the forming candle
 * moving with live prices. Its header holds the last price and the day's change, and a way to put it on a list. */
const MARKETS = ["IN", "US", "UK", "EU", "JP", "FX", "CRYPTO", "MCX", "CDS", "CMDTY"];

export function ChartPage() {
  const { market = "", symbol = "" } = useParams();
  const item = useMemo(() => itemFromPath(market, symbol), [market, symbol]);
  const known = MARKETS.includes(item.market) && /^[A-Z0-9^&._=-]{1,40}$/.test(item.symbol);
  useDocTitle(known ? `${labelOf(item)} chart` : null);
  const { notify, fail } = useApp();
  const [quote, setQuote] = useState<WatchQuote | null>(null);
  const [price, setPrice] = useState<number | null>(null);
  const [h, setH] = useState(() => Math.max(440, window.innerHeight - 330));
  const lists = useWatch();
  useEffect(() => {
    const on = () => setH(Math.max(440, window.innerHeight - 330));
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  useEffect(() => {
    if (!known) return;
    setQuote(null); setPrice(null);
    const sub = live().subscribe({ quote: (k, q) => { if (k === item.id) setQuote(q); }, tick: (k, t) => { if (k === item.id) setPrice(t.p); } });
    sub.set([item.id]);
    return () => sub.close();
  }, [item.id, known]);

  if (!known) return <div className="k-page"><EmptyState title="That chart isn't here" action={{ label: "Open Market Watch", onClick: () => openMarkets() }}>Charts are for stocks, indices, crypto, currencies and commodities. Search one in Market Watch.</EmptyState></div>;

  const p = price ?? quote?.price ?? null, c = changeOf(quote ?? undefined, price), t = changeText(c);
  const cur = item.kind === "index" || item.market === "FX" || item.market === "CRYPTO" ? "" : currencySymbol(quote?.currency ?? currencyOf(item));
  const where = lists.lists?.find((l) => l.items.some((i) => i.id === item.id));
  const addTo = async (id: string) => {
    const list = lists.lists?.find((l) => l.id === id);
    if (!list) return;
    try { await putItems(id, [...list.items, item]); notify(`Added ${labelOf(item)} to ${list.name}.`); lists.reload(); } catch (e) { fail(e); }
  };
  return (
    <div className="k-page k-stack">
      <PageHeader eyebrow={MARKET_NAME[item.market]} title={labelOf(item)} lede={subtitleOf(item) !== MARKET_NAME[item.market] ? subtitleOf(item) : undefined}
        actions={<>
          {where ? <span className="k-note">On your list {where.default ? "Watchlist" : where.name}</span>
            : lists.lists && <span className="chart-add"><Select small label="Add to a list" value="" onChange={(v) => v && void addTo(v)} options={[{ value: "", label: "Add to a list…" }, ...lists.lists.map((l) => ({ value: l.id, label: l.name }))]} /></span>}
          <button type="button" className="btn quiet sm" onClick={() => openMarkets({ open: true })}>Open Market Watch</button>
        </>} />
      <Card>
        <div className="chart-quote" aria-live="off">
          <b className="chart-px">{p == null ? "–" : `${cur}${priceText(p, quote?.currency ?? null, item.market, item.symbol)}`}</b>
          <span className={signCls(c, t)}>{c != null && c !== 0 ? (c > 0 ? "▲ " : "▼ ") : ""}{t}{c != null ? " today" : ""}</span>
          {quote?.delayed && <span className="k-note">Delayed: this price can be up to 15 minutes behind the market.</span>}
        </div>
        <ChartWorkspace item={item} height={h} />
      </Card>
      <p className="k-note">Drawings, indicators and the timeframe you pick are kept on your account for this symbol and open wherever you chart it. <Link to="/plans">What each plan keeps</Link></p>
    </div>
  );
}
