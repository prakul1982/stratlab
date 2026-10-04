import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, dateOnly, money, price, qty as qtyText, signClass } from "../lib/format";
import { AsOf, Empty, Info, Loading } from "../components/ui";
import { Download, Trash, Upload } from "../components/Icons";
import { track } from "../lib/analytics";

type Bucket = { key: string; label: string; rate: number; gains: number; after_setoff: number; exempt: number; taxable: number; tax: number };
type Sale = { key: string; bought: string; sold: string; qty: number; cost: number; sale: number; gain: number; term: "ST" | "LT"; bonus: boolean; gf: "applied" | "missing" | null; rate: number };
type Side = { gains: number; losses: number; net: number; sales: number };
type Year = {
  fy: number; label: string; stcg: Side; ltcg: Side; exempt_old: number | null; exemption: { limit: number; used: number; left: number };
  buckets: Bucket[]; steps: string[]; tax: number; tax_with_cess: number; carry_forward: { st: number; lt: number };
  intraday: { count: number; buy: number; sell: number; pnl: number }; gf_missing: number; gf_applied: number; count: number; rows: Sale[];
};
type Lot = { key: string; bought: string; qty: number; cost: number; cost_each: number | null; price: number; value: number; loss: number; loss_pct: number | null; days: number; term: "ST" | "LT"; long_from: string | null; bonus: boolean };
type Report = {
  years: Year[]; current_fy: number; names: Record<string, { symbol: string; name: string; isin: string; listed: boolean }>;
  below_cost: { rows: Lot[]; unpriced: number; open: number; st: number; lt: number };
  unmatched_sales: { key: string; qty: number; first: string }[]; holdings_check: { key: string; files: number; holdings: number }[];
  pre_2018: string[]; fmv: Record<string, { value: number | null; source: "yours" | "your file" | "looked up" | null }>;
  rules: string[]; notes: string[]; disclaimer: string; files: { name: string; broker: string; kind: string; trades: number; at: string }[];
  updated_at: string | null; trades: number; prices: boolean; prices_at: string | null; max_trades: number;
};
type Problem = { line: number | null; text: string; reason: string };
type ImportReply = { broker: string; kind: "trades" | "pnl"; read: number; added: number; duplicates: number; over_limit: number; problems: Problem[]; problem_count: number; not_listed: string[]; report: Report };

const MAX_MB = 2;
const BROKERS = "Zerodha (Console tradebook or tax P&L), Groww, Upstox, Angel One, ICICI Direct and HDFC Securities";
const inr = (v: number | null | undefined) => money(v, "INR", 0);
const rate = (r: number) => `${+(r * 100).toFixed(2)}%`;

/** The file as base64, the way the server takes it. */
function readFile(f: File): Promise<string> {
  return new Promise((ok, bad) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result));
    r.onerror = () => bad(new Error("That file couldn't be read. Pick it again."));
    r.readAsDataURL(f);
  });
}

function Disclaimer({ text }: { text: string }) {
  return <div className="banner tax-note" role="note"><span><b>Estimate only.</b> {text}</span></div>;
}

export function TaxReportPage() {
  const { fail, notify } = useApp();
  const [rep, setRep] = useState<Report | null>(null);
  const [fy, setFy] = useState<number | null>(null);
  const [mode, setMode] = useState<"add" | "replace">("add");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportReply | null>(null);
  const [allSales, setAllSales] = useState(false);
  const [getting, setGetting] = useState<"csv" | "pdf" | null>(null);
  const file = useRef<HTMLInputElement>(null);

  const show = useCallback((r: Report) => { setRep(r); setFy((cur) => (cur != null && r.years.some((y) => y.fy === cur) ? cur : r.years.find((y) => y.count || y.intraday.count)?.fy ?? r.current_fy)); }, []);
  useEffect(() => { api<Report>("/tax").then(show).catch(fail); }, [show, fail]);

  const pick = async (files: FileList | null) => {
    const list = Array.from(files ?? []);
    if (!list.length) return;
    setBusy(true);
    try {
      let last: ImportReply | null = null;
      for (const [i, f] of list.entries()) {
        if (f.size > MAX_MB * 1024 * 1024) { notify(`${f.name} is larger than ${MAX_MB} MB. Split the tradebook by year and upload each one.`); continue; }
        const data = await readFile(f);
        // with several files, only the first one replaces: the rest are added to it
        last = await api<ImportReply>("/tax/import", { method: "POST", body: { filename: f.name, data, mode: i === 0 ? mode : "add" } });
        track("tax file imported", { rows: last.added, method: mode });
      }
      if (last) { setResult(last); show(last.report); setMode("add"); }
    } catch (e) { fail(e); } finally {
      setBusy(false);
      if (file.current) file.current.value = "";
    }
  };

  const download = async (format: "csv" | "pdf") => {
    if (fy == null) return;
    setGetting(format);
    try {
      const r = await api<Response>(`/tax/export?fy=${fy}&format=${format}`, { raw: true });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await r.blob()); a.download = `stratlab-tax-FY-${fy}-${String(fy + 1).slice(2)}.${format}`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    } catch (e) { fail(e); } finally { setGetting(null); }
  };

  const remove = () => {
    if (!confirm("Delete my tax data? Every uploaded trade and file is removed from StratLab. Your broker account isn't touched.")) return;
    api("/tax", { method: "DELETE" }).then(() => { setResult(null); return api<Report>("/tax").then(show); })
      .then(() => notify("Your tax data is deleted.")).catch(fail);
  };

  const setFmv = async (symbol: string, value: number | null) => {
    try { show(await api<Report>("/tax/fmv", { method: "PUT", body: { symbol, fmv: value } })); notify(value ? `${symbol}: 31 Jan 2018 price saved.` : `${symbol}: back to the looked-up price.`); }
    catch (e) { fail(e); }
  };

  const y = useMemo(() => rep?.years.find((x) => x.fy === fy) ?? null, [rep, fy]);
  const name = (k: string) => rep?.names[k]?.symbol ?? k;
  const has = !!rep && rep.trades > 0;

  return (
    <div className="stack" style={{ gap: 24 }}>
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Tax report</span>
        <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.1 }}>Capital gains on your shares</h1>
        <p className="muted" style={{ fontSize: 17, maxWidth: 760 }}>Upload your tradebooks or tax P&amp;L files from every broker you use. StratLab matches each sale to its purchase, first in first out, and works out short- and long-term gains for each financial year at the rates that applied, the exemption used, and the set-off. Only you can see your trades, and you can delete them at any time.</p>
      </div>
      <Disclaimer text={rep?.disclaimer ?? "An estimate from the files you uploaded, not tax advice. Check it with a chartered accountant (CA) before you file or pay tax."} />

      <section className="card stack" style={{ gap: 14 }}>
        <div className="stack" style={{ gap: 4 }}>
          <h2 className="h2">Upload your trades</h2>
          <p className="small muted" style={{ margin: 0 }}>Download the equity tradebook (every trade) or the tax P&amp;L as Excel or CSV from {BROKERS}, then upload it here. You can pick several files, from several brokers, at once; trades already uploaded are skipped. Any other CSV works with the columns Date, Symbol (or ISIN), Type (buy or sell), Quantity and Price.</p>
        </div>
        <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <label className={`btn${busy ? " disabled" : ""}`} style={{ cursor: busy ? "wait" : "pointer" }}>
            <Upload size={18} />{busy ? "Reading…" : "Upload tradebook or tax P&L"}
            <input ref={file} type="file" multiple accept=".csv,.xlsx,.xls,.txt,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden disabled={busy}
              onChange={(e) => pick(e.target.files)} aria-label="Tradebook or tax P&L file" />
          </label>
          {has && (
            <div className="seg" role="radiogroup" aria-label="What the file does">
              <button role="radio" aria-checked={mode === "add"} aria-pressed={mode === "add"} onClick={() => setMode("add")}>Add to my trades</button>
              <button role="radio" aria-checked={mode === "replace"} aria-pressed={mode === "replace"} onClick={() => setMode("replace")}>Start again with this file</button>
            </div>
          )}
        </div>
        {result && (
          <div className="stack" style={{ gap: 8 }} role="status">
            <p className="small" style={{ margin: 0 }}>
              <b>{result.broker === "CSV" ? "Read as a CSV file" : `Read as a ${result.broker} ${result.kind === "pnl" ? "tax P&L" : "tradebook"}`}:</b>{" "}
              {result.added} trade{result.added === 1 ? "" : "s"} added{result.duplicates > 0 && `, ${result.duplicates} already uploaded (skipped)`}.
              {result.problem_count > 0 && ` ${result.problem_count} line${result.problem_count === 1 ? "" : "s"} left out (below).`}
              {result.over_limit > 0 && ` Only the first ${rep?.max_trades.toLocaleString()} trades are kept.`}
            </p>
            {result.not_listed.length > 0 && <p className="tiny muted" style={{ margin: 0 }}>No listed company matched {result.not_listed.slice(0, 8).join(", ")}{result.not_listed.length > 8 ? "…" : ""}. Their gains still count, without today's prices or bonus and split data.</p>}
            {result.problems.length > 0 && (
              <div className="table-wrap" style={{ margin: 0 }}>
                <table aria-label="Lines left out">
                  <thead><tr><th>Line</th><th>What the file says</th><th style={{ textAlign: "left" }}>Why</th></tr></thead>
                  <tbody>{result.problems.map((u, i) => <tr key={i}><td className="num">{u.line ?? "–"}</td><td>{u.text || "–"}</td><td style={{ textAlign: "left", whiteSpace: "normal" }} className="small muted">{u.reason}</td></tr>)}</tbody>
                </table>
              </div>
            )}
          </div>
        )}
        {has && rep && rep.files.length > 0 && (
          <p className="tiny muted" style={{ margin: 0 }}>
            {rep.trades.toLocaleString()} trades from {rep.files.length} file{rep.files.length === 1 ? "" : "s"}: {rep.files.map((f) => `${f.name} (${f.broker})`).join(", ")}{rep.updated_at ? ` · updated ${ago(rep.updated_at)}` : ""}
          </p>
        )}
      </section>

      {!rep && <Loading label="Opening your tax report" />}
      {rep && !has && (
        <Empty title="No trades yet">
          <p className="muted" style={{ maxWidth: 520 }}>Upload a tradebook or tax P&amp;L above to see your capital gains by financial year.</p>
        </Empty>
      )}

      {rep && has && y && (
        <>
          <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "flex-end", justifyContent: "space-between" }}>
            <label className="field" style={{ minWidth: 200 }}>Financial year
              <select value={fy ?? ""} onChange={(e) => { setFy(Number(e.target.value)); setAllSales(false); }} aria-label="Financial year">
                {rep.years.map((x) => <option key={x.fy} value={x.fy}>{x.label}{x.fy === rep.current_fy ? " (this year)" : ""}</option>)}
              </select>
            </label>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <button className="btn quiet sm" disabled={!!getting} onClick={() => download("csv")}><Download size={16} />{getting === "csv" ? "Making the CSV…" : "Download CSV"}</button>
              <button className="btn quiet sm" disabled={!!getting} onClick={() => download("pdf")}><Download size={16} />{getting === "pdf" ? "Making the PDF…" : "Download PDF summary"}</button>
            </div>
          </div>

          <div className="stat-row">
            <div className="stat"><span className="tiny muted">Short-term gains (net)</span><b className={`num ${signClass(y.stcg.net)}`}>{inr(y.stcg.net)}</b><span className="tiny muted">{inr(y.stcg.gains)} gains · {inr(y.stcg.losses)} losses</span></div>
            <div className="stat"><span className="tiny muted">Long-term gains (net)</span><b className={`num ${signClass(y.ltcg.net)}`}>{inr(y.ltcg.net)}</b><span className="tiny muted">{inr(y.ltcg.gains)} gains · {inr(y.ltcg.losses)} losses</span></div>
            <div className="stat"><span className="tiny muted">Long-term exemption used</span><b className="num">{inr(y.exemption.used)}</b>
              <span className="tiny muted">of {inr(y.exemption.limit)}{y.exemption.limit ? ` · ${inr(y.exemption.left)} left` : ""}</span>
              {y.exemption.limit > 0 && <div className="seg-bar" aria-hidden><i style={{ width: `${Math.max(0, Math.min(100, (y.exemption.used / y.exemption.limit) * 100))}%` }} /></div>}
            </div>
            <div className="stat"><span className="tiny muted">Estimated tax <Info label="How the tax is estimated">Short-term gains on listed shares are taxed at 15% for sales before 23 July 2024 and 20% from that day; long-term gains (held more than 12 months) at 10% and 12.5%, above the yearly exemption. Shown before the 4% cess and any surcharge.</Info></span>
              <b className="num">{inr(y.tax)}</b><span className="tiny muted">{inr(y.tax_with_cess)} with 4% cess</span></div>
          </div>

          <section className="card stack" style={{ gap: 12 }}>
            <h2 className="h2">How {y.label} adds up</h2>
            {y.buckets.length === 0 ? <p className="small muted" style={{ margin: 0 }}>No capital gains or losses were realised in {y.label}.</p> : (
              <div className="table-wrap">
                <table aria-label="Gains by rate">
                  <thead><tr><th style={{ textAlign: "left" }}>Kind</th><th>Rate</th><th>Gains</th><th>After set-off</th><th>Exempt</th><th>Taxable</th><th>Tax</th></tr></thead>
                  <tbody>{y.buckets.map((b) => (
                    <tr key={b.key}><td style={{ textAlign: "left" }}>{b.label}</td><td className="num">{rate(b.rate)}</td><td className="num">{inr(b.gains)}</td><td className="num">{inr(b.after_setoff)}</td>
                      <td className="num">{inr(b.exempt)}</td><td className="num">{inr(b.taxable)}</td><td className="num">{inr(b.tax)}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            )}
            {y.steps.length > 0 && <ul className="small" style={{ margin: 0, paddingLeft: 20 }}>{y.steps.map((s, i) => <li key={i}>{s}</li>)}</ul>}
            {y.exempt_old != null && <p className="small muted" style={{ margin: 0 }}>Long-term results on sales before 1 April 2018 ({inr(y.exempt_old)}) were exempt under the old section 10(38), so they aren't counted.</p>}
            {y.gf_missing > 0 && <p className="small" style={{ margin: 0 }}><b>{y.gf_missing} sale{y.gf_missing === 1 ? "" : "s"}</b> of shares held on 31 Jan 2018 used the actual cost, because their 31 Jan 2018 price isn't known. Grandfathering could lower that gain; enter the price below.</p>}
            {y.gf_applied > 0 && <p className="small muted" style={{ margin: 0 }}>{y.gf_applied} sale{y.gf_applied === 1 ? " was" : "s were"} grandfathered: the cost is the higher of the actual cost and the 31 Jan 2018 price (but not above the sale value).</p>}
          </section>

          <section className="card stack" style={{ gap: 10 }}>
            <h2 className="h2">Intraday trades, kept apart</h2>
            <p className="small" style={{ margin: 0 }}>{y.intraday.count ? <>{y.intraday.count} same-day round trip{y.intraday.count === 1 ? "" : "s"}: purchases {inr(y.intraday.buy)}, sales {inr(y.intraday.sell)}, result <b className={signClass(y.intraday.pnl)}>{inr(y.intraday.pnl)}</b>.</> : `No intraday trades in ${y.label}.`}</p>
            <p className="tiny muted" style={{ margin: 0 }}>Shares bought and sold on the same day are speculative business income, taxed at your slab rate, not capital gains. They aren't in the numbers above.</p>
          </section>

          {y.count > 0 && (
            <section className="card stack" style={{ gap: 12 }}>
              <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}><h2 className="h2">Each sale, matched to its purchase</h2><span className="tiny muted">{y.count} line{y.count === 1 ? "" : "s"}</span></div>
              <div className="table-wrap">
                <table aria-label="Realised sales">
                  <thead><tr><th style={{ textAlign: "left" }}>Stock</th><th>Bought</th><th>Sold</th><th>Qty</th><th>Cost</th><th>Sale</th><th>Gain or loss</th><th>Term</th><th>Rate</th></tr></thead>
                  <tbody>{(allSales ? y.rows : y.rows.slice(0, 30)).map((r, i) => (
                    <tr key={i}>
                      <td style={{ textAlign: "left" }}><b>{name(r.key)}</b>{r.bonus && <span className="tiny muted"> bonus</span>}{r.gf === "applied" && <span className="tiny muted"> grandfathered</span>}{r.gf === "missing" && <span className="tiny neg"> 31 Jan 2018 price missing</span>}</td>
                      <td className="num">{dateOnly(r.bought)}</td><td className="num">{dateOnly(r.sold)}</td><td className="num">{qtyText(r.qty)}</td>
                      <td className="num">{inr(r.cost)}</td><td className="num">{inr(r.sale)}</td><td className={`num ${signClass(r.gain)}`}>{inr(r.gain)}</td>
                      <td>{r.term === "LT" ? "Long" : "Short"}</td><td className="num">{rate(r.rate)}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
              {y.rows.length > 30 && !allSales && <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={() => setAllSales(true)}>Show all {y.rows.length}</button>}
              {y.count > y.rows.length && <p className="tiny muted" style={{ margin: 0 }}>The CSV download has all {y.count} lines.</p>}
              <p className="tiny muted" style={{ margin: 0 }}>Cost includes brokerage and charges from your files; sale is after them. STT isn't deductible, so it isn't included.</p>
            </section>
          )}

          <section className="card stack" style={{ gap: 12 }}>
            <div className="row" style={{ gap: 6, alignItems: "center", flexWrap: "wrap" }}>
              <h2 className="h2">Open lots below cost</h2>
              <Info label="What is tax-loss harvesting?">Tax-loss harvesting is a name for realising a loss on shares that are below their cost, so the loss can be set off against gains in the same financial year. India has no specific wash-sale rule today; shares bought again start a new holding period at the new price. Whether it suits anyone depends on their whole tax position, so check with a CA.</Info>
            </div>
            <p className="small muted" style={{ margin: 0 }}>Lots still open in your files that are worth less than they cost at today's price, and how long each has been held. Facts only: this is not a suggestion to do anything.</p>
            {rep.below_cost.rows.length === 0 ? <p className="small" style={{ margin: 0 }}>{rep.below_cost.open ? "No open lot is below its cost at today's price." : "Your files leave no shares open."}</p> : (
              <>
                <p className="small" style={{ margin: 0 }}>Below cost now: <b className="neg">{inr(rep.below_cost.st)}</b> on short-term lots and <b className="neg">{inr(rep.below_cost.lt)}</b> on long-term lots.</p>
                <div className="table-wrap">
                  <table aria-label="Open lots below cost">
                    <thead><tr><th style={{ textAlign: "left" }}>Stock</th><th>Bought</th><th>Qty</th><th>Cost a share</th><th>Price now</th><th>Below cost by</th><th>Held</th><th>Term today</th></tr></thead>
                    <tbody>{rep.below_cost.rows.map((r, i) => (
                      <tr key={i}>
                        <td style={{ textAlign: "left" }}><Link className="link" to={`/research/IN/${encodeURIComponent(r.key)}`}><b>{name(r.key)}</b></Link>{r.bonus && <span className="tiny muted"> bonus</span>}</td>
                        <td className="num">{dateOnly(r.bought)}</td><td className="num">{qtyText(r.qty)}</td><td className="num">{price(r.cost_each, "INR")}</td><td className="num">{price(r.price, "INR")}</td>
                        <td className="num neg">{inr(r.loss)}{r.loss_pct != null && <span className="tiny"> {r.loss_pct.toFixed(1)}%</span>}</td>
                        <td className="num">{r.days} days</td>
                        <td className="small">{r.term === "LT" ? "Long-term" : <>Short-term<div className="tiny muted">long-term from {dateOnly(r.long_from)}</div></>}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              </>
            )}
            {rep.below_cost.unpriced > 0 && <p className="tiny muted" style={{ margin: 0 }}>{rep.below_cost.unpriced} open lot{rep.below_cost.unpriced === 1 ? " has" : "s have"} no price today{rep.prices ? " (not a listed company we could match)" : " (live prices are offline right now)"}.</p>}
            <AsOf parts={[["Prices", rep.prices_at]]} />
          </section>

          {(rep.holdings_check.length > 0 || rep.unmatched_sales.length > 0) && (
            <section className="card stack" style={{ gap: 10 }}>
              <h2 className="h2">Worth checking</h2>
              {rep.unmatched_sales.map((u) => (
                <p key={u.key} className="small" style={{ margin: 0 }}><b>{name(u.key)}</b>: {qtyText(u.qty)} shares sold (first on {dateOnly(u.first)}) with no matching purchase in your files. They may have been bought before your earliest file, moved in from another account, or come from a bonus or split older than our data. Their gain isn't counted; upload the older tradebook to include it.</p>
              ))}
              {rep.holdings_check.map((h) => (
                <p key={h.key} className="small" style={{ margin: 0 }}><b>{name(h.key)}</b>: your files leave {qtyText(h.files)} shares open; <Link className="link" to="/holdings">My Holdings</Link> has {qtyText(h.holdings)}.</p>
              ))}
            </section>
          )}

          {rep.pre_2018.length > 0 && (
            <section className="card stack" style={{ gap: 12 }}>
              <div className="row" style={{ gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <h2 className="h2">Shares held on 31 Jan 2018</h2>
                <Info label="What is grandfathering?">For listed shares bought before 1 February 2018, the cost used for long-term gains is the higher of the actual cost and the share's highest price on 31 January 2018, but not more than the sale value. Gains made up to that day stay untaxed.</Info>
              </div>
              <div className="stack" style={{ gap: 10 }}>
                {rep.pre_2018.map((k) => <FmvRow key={k} symbol={name(k)} id={k} fmv={rep.fmv[k]} onSave={setFmv} />)}
              </div>
              <p className="tiny muted" style={{ margin: 0 }}>Looked-up prices come from stored price history and are adjusted for later bonuses and splits we know of. Check them against the exchange's 31 Jan 2018 price list, and enter your own if they differ.</p>
            </section>
          )}

          <section className="card stack" style={{ gap: 10 }}>
            <h2 className="h2">The set-off rules, in plain words</h2>
            <ul className="small" style={{ margin: 0, paddingLeft: 20 }}>{rep.rules.map((r, i) => <li key={i}>{r}</li>)}</ul>
            <h3 className="small" style={{ margin: "6px 0 0" }}>How this report works</h3>
            <ul className="small muted" style={{ margin: 0, paddingLeft: 20 }}>{rep.notes.map((r, i) => <li key={i}>{r}</li>)}</ul>
          </section>
        </>
      )}

      {rep && has && (
        <section className="stack" style={{ gap: 8 }}>
          <p className="small muted" style={{ margin: 0, maxWidth: "80ch" }}>Your trades are stored with your account only, used for this page, and never shared. Delete them at any time.</p>
          <button className="btn danger" style={{ alignSelf: "flex-start" }} onClick={remove}><Trash size={16} />Delete my tax data</button>
        </section>
      )}
      <Disclaimer text={rep?.disclaimer ?? "An estimate, not tax advice. Check it with a chartered accountant (CA)."} />
    </div>
  );
}

function FmvRow({ symbol, id, fmv, onSave }: { symbol: string; id: string; fmv?: { value: number | null; source: string | null }; onSave: (symbol: string, value: number | null) => void }) {
  const [v, setV] = useState("");
  const n = Number(v.replace(/,/g, ""));
  const where = fmv?.source === "yours" ? "your price" : fmv?.source === "your file" ? "from your broker's file" : fmv?.source === "looked up" ? "looked up" : "not known";
  return (
    <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
      <div className="stack" style={{ gap: 2, minWidth: 160 }}>
        <b>{symbol}</b>
        <span className="tiny muted">{fmv?.value ? `${price(fmv.value, "INR")} a share, ${where}` : where === "from your broker's file" ? "from your broker's file" : "31 Jan 2018 price not known"}</span>
      </div>
      <label className="field" style={{ width: 170 }}>Your 31 Jan 2018 price (₹)<input value={v} inputMode="decimal" placeholder="e.g. 310.50" onChange={(e) => setV(e.target.value)} /></label>
      <button className="btn quiet sm" disabled={!(n > 0)} onClick={() => { onSave(id, n); setV(""); }} aria-label={`Save the 31 Jan 2018 price for ${symbol}`}>Save</button>
      {fmv?.source === "yours" && <button className="btn quiet sm" onClick={() => onSave(id, null)} aria-label={`Clear my price for ${symbol}`}>Clear</button>}
    </div>
  );
}
