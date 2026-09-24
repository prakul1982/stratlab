import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useApp } from "../lib/app";
import { riskForCurrency } from "../lib/rules";
import type { Instrument, Market } from "../lib/types";
import { parseCsv, saveUpload, type Candle } from "../lib/upload";
import { InstrumentSearch } from "../components/InstrumentSearch";
import { Info, Loading } from "../components/ui";
import { HELP } from "../lib/help";
import { useNotebook } from "./NotebookPage";

function localHours(m: Market): string {
  if (!m.hours) return "Your own session hours";
  if (!m.hours.open || !m.hours.close) return m.hours.days;
  // show the session in the viewer's own time zone
  const today = new Date();
  const toLocal = (hm: string) => {
    const [h, mi] = hm.split(":").map(Number);
    const guess = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate(), h, mi);
    const parts = new Intl.DateTimeFormat("en-US", { timeZone: m.tz, year: "numeric", month: "numeric", day: "numeric",
      hour: "numeric", minute: "numeric", hourCycle: "h23" }).formatToParts(new Date(guess));
    const get = (t: string) => +(parts.find((p) => p.type === t)?.value ?? 0);
    const shown = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"));
    const instant = guess - (shown - guess);   // the moment the market's clock reads h:mi
    return new Date(instant).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
  };
  return `${toLocal(m.hours.open)}–${toLocal(m.hours.close)} your time, ${m.hours.days}`;
}

const STATUS: Record<Market["status"], string> = { live: "Live", offline: "Offline", soon: "Coming soon" };

export function MarketPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const { markets, notify } = useApp();
  const { nb, patch, flush } = useNotebook(id);
  const [sel, setSel] = useState<string | null>(null);
  const [upload, setUpload] = useState<{ bars: Candle[]; skipped: number; file: string } | null>(null);
  const [upName, setUpName] = useState("");
  const [upCur, setUpCur] = useState("USD");
  const [upStep, setUpStep] = useState(1);
  const loc = useLocation();

  useEffect(() => {
    if (!nb || sel) return;
    const asked = (loc.state as { market?: string } | null)?.market;
    const current = nb.instrument && "market" in nb.instrument ? nb.instrument.market : null;
    setSel(asked || current || markets.find((m) => m.status === "live" && m.id !== "CSV")?.id || "CRYPTO");
  }, [nb, markets, sel, loc.state]);

  if (!nb) return <Loading label="Opening markets" />;
  const market = markets.find((m) => m.id === sel);

  const choose = async (i: Instrument) => {
    patch({ instrument: i, instrumentId: i.id, strategy: { ...nb.strategy, risk: riskForCurrency(nb.strategy.risk, i.currency) } }, true);
    await flush();
    nav(`/n/${nb.id}`);
  };

  const onFile = async (f: File | undefined) => {
    if (!f) return;
    try {
      const parsed = parseCsv(await f.text());
      setUpload({ ...parsed, file: f.name });
      setUpName(f.name.replace(/\.(csv|txt)$/i, "").slice(0, 60));
    } catch (e) { notify((e as Error).message); }
  };

  const useUpload = async () => {
    if (!upload) return;
    const name = upName.trim() || "Uploaded data";
    saveUpload(nb.id, { name, currency: upCur, step: upStep, bars: upload.bars });
    patch({ instrument: { id: "CSV:upload", symbol: name, market: "CSV", currency: upCur }, instrumentId: `CSV:${name}` }, true);
    await flush();
    nav(`/n/${nb.id}`);
  };

  return (
    <div className="stack" style={{ gap: 26 }}>
      <div className="stack" style={{ gap: 8 }}>
        <Link to={`/n/${nb.id}`} className="link" style={{ textDecoration: "none", alignSelf: "flex-start" }}>← {nb.name}</Link>
        <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 48px)", fontWeight: 400, letterSpacing: "-0.02em" }}>Where do you want to test it?</h1>
        <p className="muted row" style={{ fontSize: 17, gap: 0 }}>The same rules run on any market. Prices, trading hours, currency and costs switch to match it.<Info>{HELP.markets}</Info></p>
      </div>

      <div className="grid4" role="radiogroup" aria-label="Market">
        {markets.map((m) => (
          <button key={m.id} role="radio" aria-checked={sel === m.id} className="card" onClick={() => setSel(m.id)}
            style={{ textAlign: "left", cursor: "pointer", display: "flex", flexDirection: "column", gap: 12, minHeight: 210,
              border: sel === m.id ? "2px solid var(--ink)" : undefined, opacity: m.status === "soon" ? 0.72 : 1 }}>
            <div className="spread" style={{ alignItems: "flex-start" }}>
              <span className="serif" style={{ fontSize: 38, lineHeight: 1 }}>{m.symbol}</span>
              <span className={`badge ${m.status}`}>{STATUS[m.status]}</span>
            </div>
            <div className="stack" style={{ gap: 1 }}><b style={{ fontSize: 17 }}>{m.name}</b><span className="small muted">{m.venues}</span></div>
            <div className="mono stack" style={{ gap: 4, fontSize: 12.5, color: "var(--ink-2)", paddingTop: 10, borderTop: "1px solid var(--line)" }}>
              <span>{m.what}</span><span>{localHours(m)}</span><span>{m.costs}</span>
            </div>
          </button>
        ))}
      </div>

      {market && market.status === "soon" && (
        <div className="card dashed stack">
          <h2 className="h2">{market.name} is coming soon</h2>
          <p className="muted">We're connecting a data source for {market.name}. Meanwhile, you can export candles from any charting site as a CSV and test on them with <button className="link" onClick={() => setSel("CSV")}>your own data</button>.</p>
        </div>
      )}
      {market && market.status === "offline" && (
        <div className="banner">Market data for {market.name} is offline right now. It usually comes back after the daily data login; try again in a few minutes.</div>
      )}

      {market && market.status === "live" && market.id !== "CSV" && <InstrumentSearch market={market} onPick={choose} autoFocus />}

      {market?.id === "CSV" && (
        <div className="card stack" style={{ gap: 14 }}>
          <h2 className="h2 row" style={{ gap: 0 }}>Upload candles as a CSV<Info label="What should the file look like?">{HELP.csv}</Info></h2>
          <p className="muted">Any market, any timeframe. The first row should be headings: <span className="mono">date, open, high, low, close, volume</span>. Most charting sites and brokers can export this.</p>
          <label className="btn outline" style={{ alignSelf: "flex-start" }}>
            Choose a CSV file
            <input type="file" accept=".csv,text/csv,.txt" className="sr-only" onChange={(e) => onFile(e.target.files?.[0])} />
          </label>
          {upload && (
            <>
              <p className="small">
                <b>{upload.bars.length.toLocaleString()} candles</b> from {new Date(upload.bars[0].t).toLocaleDateString("en-GB")} to {new Date(upload.bars[upload.bars.length - 1].t).toLocaleDateString("en-GB")}
                {upload.skipped ? `, ${upload.skipped} rows skipped` : ""}.
              </p>
              <div className="grid4">
                <label className="field">Name<input value={upName} maxLength={60} onChange={(e) => setUpName(e.target.value)} /></label>
                <label className="field">Currency<select value={upCur} onChange={(e) => setUpCur(e.target.value)}>
                  {["USD", "INR", "EUR", "GBP", "JPY", "USDT"].map((c) => <option key={c}>{c}</option>)}</select></label>
                <label className="field"><span className="row" style={{ gap: 0 }}>Quantities<Info>{HELP.quantities}</Info></span><select value={upStep} onChange={(e) => setUpStep(+e.target.value)}>
                  <option value={1}>Whole units (shares, lots)</option><option value={0.0001}>Fractions (coins, forex)</option></select></label>
              </div>
              <button className="btn blue" style={{ alignSelf: "flex-start" }} onClick={useUpload}>Test on this data</button>
              <p className="hint">The file stays in this browser; only the candles are sent for each test.</p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
