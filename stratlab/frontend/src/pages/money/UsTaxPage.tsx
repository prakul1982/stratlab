import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { ago, dateOnly, money, qty as qtyText, signClass } from "../../lib/format";
import { Empty, Info, Loading } from "../../components/ui";
import { Download, Trash, Upload } from "../../components/Icons";
import { track } from "../../lib/analytics";

// ---------- what the server sends ----------
type Rate = { rate: number; on: string; fallback: boolean } | null;
type Sale = {
  symbol: string; bought: string; sold: string; qty: number; cost_usd: number; sale_usd: number; rate_buy: Rate; rate_sell: Rate;
  cost: number | null; indexed_cost: number | null; sale: number | null; gain: number | null; term: "ST" | "LT"; rate: number | null; bucket: string;
};
type Ftc = { income: number; foreign_tax: number; indian_tax: number; credit: number; not_credited: number };
type DivStock = { symbol: string; count: number; usd: number; tax_usd: number; inr: number; tax_inr: number; fallback: boolean; ftc: Ftc };
type Dividends = { fy: number; stocks: DivStock[]; usd: number; inr: number; tax_inr: number; ftc: Ftc; indian_rate: number; unpriced: number; estimated: boolean };
type Year = { fy: number; label: string; count: number; unpriced: number; st: number; lt: number; sale: number; fallback: boolean; rows?: Sale[]; dividends?: Dividends };
type FaRow = {
  symbol: string; name: string; lot: number; acquired: string; country: string; nature: string; initial: number | null; initial_usd: number;
  peak: number | null; peak_day: string | null; closing: number | null; closing_qty: number; income: number; proceeds: number | null;
};
type Fa = { cy: number; label: string; rows: FaRow[]; totals: Record<string, number>; missing_prices: string[]; missing_rates: number; fallback: boolean };
type Trade = { id: string; d: string; side: "B" | "S"; sym: string; qty: number; price: number; fees?: number; src?: string };
type View = {
  as_of: string; fy: number; cy: number; cys: number[]; locked: boolean; plan: string; trades: Trade[]; files: { name: string; rows: number; at: string }[];
  gaps: { symbol: string; name: string; held: number; in_trades: number; missing: number; avg: number | null }[]; short: Record<string, number>;
  open_lots: { symbol: string; bought: string; qty: number; cost_usd: number; term: "ST" | "LT"; long_from: string | null }[];
  years: Year[]; fa: Fa | null; facts: string[]; assumptions: string[]; missing_history: string[];
  rates: { available: boolean; sbi_from: string | null; sbi_to: string | null; source: string; fallback: string }; names: Record<string, string>;
};
type ImportReply = { read: number; added: number; duplicates: number; problems: { line: number; text: string; reason: string }[]; month_first: boolean; us: View };

const inr = (v: number | null | undefined) => money(v, "INR", 0);
const usd = (v: number | null | undefined) => money(v, "USD", 2);
const rateText = (r: Rate) => (r ? `₹${r.rate.toFixed(2)} (${dateOnly(r.on)}${r.fallback ? ", RBI" : ""})` : "not known");
const today = () => new Date().toISOString().slice(0, 10);
const blank = { d: "", side: "B" as "B" | "S", sym: "", qty: "", price: "", fees: "" };

function Locked({ text }: { text: string }) {
  return <div className="banner" role="note"><span>{text} <Link className="link" to="/plans">See plans</Link></span></div>;
}

export function UsTaxPage() {
  const { fail, notify } = useApp();
  const [v, setV] = useState<View | null>(null);
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [getting, setGetting] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  const load = useCallback((fy?: number, cy?: number) => {
    const q = new URLSearchParams();
    if (fy) q.set("fy", String(fy));
    if (cy) q.set("cy", String(cy));
    return api<View>(`/money/us-tax${q.size ? `?${q}` : ""}`).then(setV).catch(fail);
  }, [fail]);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    const body = { d: form.d, side: form.side, sym: form.sym.trim().toUpperCase(), qty: Number(form.qty), price: Number(form.price), fees: Number(form.fees || 0) };
    if (!body.d || !body.sym || !(body.qty > 0) || !(body.price >= 0) || form.price === "") { notify("Fill in the date, ticker, shares and price."); return; }
    setBusy(true);
    try {
      setV(await api<View>("/money/us-tax/trades", { method: "POST", body }));
      setForm(blank);
      notify(`${body.side === "B" ? "Purchase" : "Sale"} of ${body.sym} added.`);
      track("us trade added", { side: body.side });
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const pick = async (files: FileList | null) => {
    const f = files?.[0];
    if (!f) return;
    if (f.size > 5 * 1024 * 1024) { notify("That file is larger than 5 MB."); return; }
    setBusy(true);
    try {
      const r = await api<ImportReply>(`/money/us-tax/import?${new URLSearchParams({ filename: f.name.slice(0, 200) })}`, { method: "POST", file: f });
      setV(r.us);
      setNote(`${r.added} trade${r.added === 1 ? "" : "s"} added${r.duplicates ? `, ${r.duplicates} already there (skipped)` : ""}${r.problems.length ? `, ${r.problems.length} line${r.problems.length === 1 ? "" : "s"} left out` : ""}.${r.month_first ? " Dates like 03/04/2025 were read month first, the US way." : ""}`);
      track("us trades imported", { rows: r.added });
    } catch (e) { fail(e); } finally { setBusy(false); if (file.current) file.current.value = ""; }
  };
  const removeOne = async (id: string) => {
    try { setV(await api<View>(`/money/us-tax/trades/${encodeURIComponent(id)}`, { method: "DELETE" })); } catch (e) { fail(e); }
  };
  const removeAll = async () => {
    if (!confirm("Delete all your US trades from StratLab? Your broker account isn't touched.")) return;
    try { await api("/money/us-tax", { method: "DELETE" }); setNote(null); await load(); notify("Your US trades are deleted."); } catch (e) { fail(e); }
  };
  const faCsv = async () => {
    if (!v?.fa) return;
    setGetting(true);
    try {
      const r = await api<Response>(`/money/us-tax/schedule-fa.csv?cy=${v.fa.cy}`, { raw: true });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await r.blob()); a.download = `stratlab-schedule-FA-CY${v.fa.cy}.csv`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    } catch (e) { fail(e); } finally { setGetting(false); }
  };

  const y = v?.years.find((x) => x.fy === v.fy) ?? v?.years[0];
  const set = (k: keyof typeof blank) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div className="stack" style={{ gap: 24 }}>
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Money · US stocks</span>
        <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.1 }}>US stocks in Indian tax</h1>
        <p className="muted" style={{ fontSize: 17, maxWidth: 760 }}>Your US share sales in rupees the way the Income-tax Rules convert them, long or short term under the 24-month rule, US dividends with the tax withheld and the foreign tax credit, and the calendar-year Schedule FA table. Only you can see these figures.</p>
      </div>
      <div className="banner tax-note" role="note"><span><b>Estimate only.</b> Arithmetic on your own trades, not tax advice, for a resident individual. Check it with a chartered accountant (CA) before you file.</span></div>

      <section className="card stack" style={{ gap: 14 }}>
        <div className="stack" style={{ gap: 4 }}>
          <h2 className="h2">Your US trades</h2>
          <p className="small muted" style={{ margin: 0 }}>Upload your US broker's trade history as CSV or Excel (columns for the date, purchase or sale, the ticker, shares and the price in dollars; fees optional), or add each purchase and sale below. Dates are best as YYYY-MM-DD.</p>
        </div>
        <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <label className={`btn quiet${busy ? " disabled" : ""}`} style={{ cursor: busy ? "wait" : "pointer" }}>
            <Upload size={18} />{busy ? "Reading…" : "Upload US trades"}
            <input ref={file} type="file" accept=".csv,.xlsx,.txt,text/csv" hidden disabled={busy} onChange={(e) => pick(e.target.files)} aria-label="US trades file" />
          </label>
          {!!v?.trades.length && <button className="btn quiet sm" onClick={removeAll}><Trash size={16} />Delete all US trades</button>}
        </div>
        {note && <p className="small" role="status" style={{ margin: 0 }}>{note}</p>}
        <div className="us-form" role="group" aria-label="Add a trade">
          <label className="field">Date<input type="date" value={form.d} max={today()} onChange={set("d")} aria-label="Trade date" /></label>
          <label className="field">Trade
            <select value={form.side} onChange={set("side")} aria-label="Purchase or sale"><option value="B">Purchase</option><option value="S">Sale</option></select>
          </label>
          <label className="field">Ticker<input value={form.sym} onChange={set("sym")} placeholder="AAPL" maxLength={10} aria-label="Ticker" /></label>
          <label className="field">Shares<input type="number" inputMode="decimal" min={0} step="any" value={form.qty} onChange={set("qty")} aria-label="Shares" /></label>
          <label className="field">Price ($)<input type="number" inputMode="decimal" min={0} step="any" value={form.price} onChange={set("price")} aria-label="Price in dollars" /></label>
          <label className="field">Fees ($)<input type="number" inputMode="decimal" min={0} step="any" value={form.fees} onChange={set("fees")} aria-label="Fees in dollars" /></label>
          <button className="btn" disabled={busy} onClick={add}>Add trade</button>
        </div>
        {v && v.gaps.length > 0 && (
          <div className="stack" style={{ gap: 6 }} aria-label="Holdings without purchases">
            {v.gaps.map((g) => (
              <p key={g.symbol} className="small" style={{ margin: 0 }}>
                <b>{g.symbol}</b>: <Link className="link" to="/holdings">My Holdings</Link> has {qtyText(g.held)} shares; your trades cover {qtyText(g.in_trades)}.{" "}
                <button className="btn quiet sm" onClick={() => setForm({ ...blank, sym: g.symbol, qty: String(g.missing), price: g.avg ? String(g.avg) : "" })}>Add its purchase</button>
              </p>
            ))}
          </div>
        )}
        {v && Object.keys(v.short).length > 0 && (
          <p className="small" style={{ margin: 0 }}>Sold with no purchase in your trades: {Object.entries(v.short).map(([s, q]) => `${s} (${qtyText(q)} shares)`).join(", ")}. Their gain isn't counted; add the purchases.</p>
        )}
        {v && v.trades.length > 0 && (
          <details>
            <summary className="small">{v.trades.length} trade{v.trades.length === 1 ? "" : "s"}{v.files.length ? ` · last file ${ago(v.files[v.files.length - 1].at)}` : ""}</summary>
            <div className="table-wrap" style={{ marginTop: 8 }}>
              <table aria-label="US trades">
                <thead><tr><th style={{ textAlign: "left" }}>Date</th><th>Trade</th><th>Ticker</th><th>Shares</th><th>Price</th><th>Fees</th><th></th></tr></thead>
                <tbody>{v.trades.slice(0, 200).map((t, i) => (
                  <tr key={t.id || i}>
                    <td style={{ textAlign: "left" }}>{dateOnly(t.d)}</td><td>{t.side === "B" ? "Purchase" : "Sale"}</td><td><b>{t.sym}</b></td>
                    <td className="num">{qtyText(t.qty)}</td><td className="num">{usd(t.price)}</td><td className="num">{usd(t.fees ?? 0)}</td>
                    <td>{t.id && <button className="btn quiet sm" aria-label={`Delete the ${t.sym} trade of ${t.d}`} onClick={() => removeOne(t.id)}><Trash size={14} /></button>}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </details>
        )}
      </section>

      {!v && <Loading label="Opening your US stocks" />}
      {v && v.trades.length === 0 && (
        <Empty title="No US trades yet">
          <p className="muted" style={{ maxWidth: 560 }}>Add your US purchases and sales above to see each sale's gain in rupees, which lots are long term, and the Schedule FA table.</p>
        </Empty>
      )}

      {v && v.trades.length > 0 && y && (
        <>
          {!v.rates.available && <div className="banner" role="note"><span>The rupee rates couldn't be loaded just now, so the rupee figures are missing. Try again in a while.</span></div>}
          <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
            <label className="field" style={{ minWidth: 200 }}>Financial year
              <select value={y.fy} onChange={(e) => load(Number(e.target.value), v.cy)} aria-label="Financial year">
                {v.years.map((x) => <option key={x.fy} value={x.fy}>{x.label}</option>)}
              </select>
            </label>
          </div>
          <div className="stat-row">
            <div className="stat"><span className="tiny muted">Short-term gain (held 24 months or less)</span><b className={`num ${signClass(y.st)}`}>{inr(y.st)}</b><span className="tiny muted">at your slab rate</span></div>
            <div className="stat"><span className="tiny muted">Long-term gain <Info label="How US shares are taxed">Shares listed abroad are taxed like unlisted shares in India: long term when held more than 24 months, at 12.5% without indexation for sales from 23 July 2024 (20% with indexation before), with no ₹1.25 lakh exemption. Short-term gains are added to your income at your slab rate.</Info></span><b className={`num ${signClass(y.lt)}`}>{inr(y.lt)}</b><span className="tiny muted">12.5% (section 112)</span></div>
            <div className="stat"><span className="tiny muted">Sales in {y.label}</span><b className="num">{y.count}</b><span className="tiny muted">{inr(y.sale)} sale value</span></div>
          </div>
          {y.unpriced > 0 && <p className="small" style={{ margin: 0 }}>{y.unpriced} sale{y.unpriced === 1 ? " has" : "s have"} no rupee rate for its dates yet, so {y.unpriced === 1 ? "it isn't" : "they aren't"} counted.</p>}
          <p className="small muted" style={{ margin: "-8px 0 0" }}>These sales are in your <Link className="link" to="/tax-report">tax report</Link> too, where losses are set off against your other gains, and in the <Link className="link" to="/money/itr">ITR-ready export</Link>.</p>

          {v.locked ? <Locked text={`Each sale's rupee workings, US dividends with the foreign tax credit, and Schedule FA are on the ${v.plan} plan.`} /> : (
            <>
              <section className="card stack" style={{ gap: 12 }}>
                <h2 className="h2">Each sale in rupees</h2>
                {!y.rows?.length ? <p className="small muted" style={{ margin: 0 }}>No US sales in {y.label}.</p> : (
                  <div className="table-wrap">
                    <table aria-label="US sales in rupees">
                      <thead><tr><th style={{ textAlign: "left" }}>Stock</th><th>Bought</th><th>Sold</th><th>Shares</th><th>Cost</th><th>Rate used</th><th>Cost (₹)</th><th>Sale</th><th>Rate used</th><th>Sale (₹)</th><th>Gain (₹)</th><th>Term</th></tr></thead>
                      <tbody>{y.rows.map((r, i) => (
                        <tr key={i}>
                          <td style={{ textAlign: "left" }}><b>{r.symbol}</b></td><td className="num">{dateOnly(r.bought)}</td><td className="num">{dateOnly(r.sold)}</td>
                          <td className="num">{qtyText(r.qty)}</td><td className="num">{usd(r.cost_usd)}</td><td className="small">{rateText(r.rate_buy)}</td>
                          <td className="num">{inr(r.indexed_cost ?? r.cost)}{r.indexed_cost != null && <div className="tiny muted">indexed</div>}</td>
                          <td className="num">{usd(r.sale_usd)}</td><td className="small">{rateText(r.rate_sell)}</td><td className="num">{inr(r.sale)}</td>
                          <td className={`num ${signClass(r.gain)}`}>{inr(r.gain)}</td>
                          <td>{r.term === "LT" ? `Long, ${r.rate === 0.2 ? "20%" : "12.5%"}` : "Short, slab"}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                )}
                <p className="tiny muted" style={{ margin: 0 }}>Rule 115: the sale at SBI's TT buying rate on the last day of the month before the sale, the cost at the rate on the last day of the month before the purchase; the last rate SBI published when it has none that day. "RBI" marks the RBI reference rate, used where SBI's rate isn't known.</p>
              </section>

              <section className="card stack" style={{ gap: 12 }}>
                <div className="row" style={{ gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                  <h2 className="h2">US dividends and the foreign tax credit</h2>
                  <Info label="How the credit works">The US withholds 25% of dividends paid to an Indian resident who gave the broker a W-8BEN (India-US treaty, Article 10). India taxes the dividend at your slab rate and gives credit for the US tax, but never more than the Indian tax on that dividend. You claim it by filing Form 67 by the end of the assessment year.</Info>
                </div>
                {!y.dividends || !y.dividends.stocks.length ? <p className="small muted" style={{ margin: 0 }}>No US dividends in {y.label}.</p> : (
                  <>
                    <div className="table-wrap">
                      <table aria-label="US dividends and credit">
                        <thead><tr><th style={{ textAlign: "left" }}>Stock</th><th>Dividends</th><th>US tax</th><th>Dividends (₹)</th><th>US tax (₹)</th><th>Indian tax on it (₹)</th><th>Credit (₹)</th></tr></thead>
                        <tbody>{y.dividends.stocks.map((s) => (
                          <tr key={s.symbol}><td style={{ textAlign: "left" }}><b>{s.symbol}</b></td><td className="num">{usd(s.usd)}</td><td className="num">{usd(s.tax_usd)}</td>
                            <td className="num">{inr(s.inr)}</td><td className="num">{inr(s.tax_inr)}</td><td className="num">{inr(s.ftc.indian_tax)}</td><td className="num">{inr(s.ftc.credit)}</td></tr>
                        ))}</tbody>
                      </table>
                    </div>
                    <p className="small" style={{ margin: 0 }}>Credit for {y.label}: <b>{inr(y.dividends.ftc.credit)}</b> of the {inr(y.dividends.tax_inr)} US tax{y.dividends.ftc.not_credited > 0.5 ? `; ${inr(y.dividends.ftc.not_credited)} can't be credited (more than the Indian tax on the dividends)` : ""}. Indian tax on the dividends at your average rate of {(y.dividends.indian_rate * 100).toFixed(2)}% from the <Link className="link" to="/tax-report">total tax estimate</Link>.</p>
                    {y.dividends.estimated && <p className="tiny muted" style={{ margin: 0 }}>Estimated: each dividend the company paid × the shares your trades held on its ex-date, dated by the ex-date. Upload your broker's dividend statement in <Link className="link" to="/money/tax-tools">Tax tools</Link> for the actual figures.</p>}
                  </>
                )}
              </section>
            </>
          )}

          <section className="card stack" style={{ gap: 12 }}>
            <h2 className="h2">Shares you still hold</h2>
            {!v.open_lots.length ? <p className="small muted" style={{ margin: 0 }}>Your trades leave no US shares open.</p> : (
              <div className="table-wrap">
                <table aria-label="Open US lots">
                  <thead><tr><th style={{ textAlign: "left" }}>Stock</th><th>Bought</th><th>Shares</th><th>Cost</th><th>Term today</th></tr></thead>
                  <tbody>{v.open_lots.map((l, i) => (
                    <tr key={i}><td style={{ textAlign: "left" }}><b>{l.symbol}</b></td><td className="num">{dateOnly(l.bought)}</td><td className="num">{qtyText(l.qty)}</td>
                      <td className="num">{usd(l.cost_usd)}</td><td className="small">{l.term === "LT" ? "Long-term" : <>Short-term<div className="tiny muted">long-term from {dateOnly(l.long_from)}</div></>}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            )}
            <p className="tiny muted" style={{ margin: 0 }}>Facts only: when each lot turns long term under the 24-month rule. Not a suggestion to do anything.</p>
          </section>

          {!v.locked && v.fa && (
            <section className="card stack" style={{ gap: 12 }} aria-label="Schedule FA">
              <div className="spread" style={{ gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
                <div className="row" style={{ gap: 6, alignItems: "center" }}>
                  <h2 className="h2">Schedule FA, Table A3</h2>
                  <Info label="What Schedule FA is">Residents list every foreign asset held at any time in the calendar year (1 January to 31 December) in Schedule FA of ITR-2 or ITR-3. Table A3 takes one line per purchase lot of foreign shares, with the initial, peak and closing value and the income, each at SBI's TT buying rate on its own date.</Info>
                </div>
                <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
                  <label className="field">Calendar year
                    <select value={v.fa.cy} onChange={(e) => load(v.fy, Number(e.target.value))} aria-label="Calendar year">
                      {v.cys.map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </label>
                  <button className="btn quiet sm" disabled={getting} onClick={faCsv}><Download size={16} />{getting ? "Making the CSV…" : "Download CSV"}</button>
                </div>
              </div>
              <p className="small muted" style={{ margin: 0 }}>{v.fa.label}.</p>
              {!v.fa.rows.length ? <p className="small" style={{ margin: 0 }}>No US shares were held in {v.fa.cy}.</p> : (
                <div className="table-wrap">
                  <table aria-label="Schedule FA">
                    <thead><tr><th style={{ textAlign: "left" }}>Entity</th><th>Acquired</th><th>Initial value</th><th>Peak value</th><th>Closing balance</th><th>Income credited</th><th>Sale proceeds</th></tr></thead>
                    <tbody>{v.fa.rows.map((r) => (
                      <tr key={`${r.symbol}-${r.lot}`}>
                        <td style={{ textAlign: "left" }}><b>{r.name}</b><div className="tiny muted">{r.symbol} · lot {r.lot}</div></td><td className="num">{dateOnly(r.acquired)}</td>
                        <td className="num">{inr(r.initial)}</td><td className="num">{inr(r.peak)}{r.peak_day && <div className="tiny muted">{dateOnly(r.peak_day)}</div>}</td>
                        <td className="num">{inr(r.closing)}</td><td className="num">{inr(r.income)}</td><td className="num">{r.proceeds == null ? "–" : inr(r.proceeds)}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
              {v.fa.missing_prices.length > 0 && <p className="small" style={{ margin: 0 }}>No daily prices for {v.fa.missing_prices.join(", ")}, so their peak and closing values are blank. Use your broker's year statement for them.</p>}
              <p className="tiny muted" style={{ margin: 0 }}>Country: 2-UNITED STATES OF AMERICA; nature of entity: company. Fill each company's address and ZIP code from its annual report. The broker account's cash goes in Table A2, from your broker's statement.</p>
            </section>
          )}
        </>
      )}

      <section className="card stack" style={{ gap: 10 }}>
        <h2 className="h2">Deadlines and rules</h2>
        <ul className="small" style={{ margin: 0, paddingLeft: 20 }} aria-label="Deadlines and rules">{(v?.facts ?? []).map((f, i) => <li key={i}>{f}</li>)}</ul>
        <h3 className="small" style={{ margin: "6px 0 0" }}>How these figures are worked out</h3>
        <ul className="small muted" style={{ margin: 0, paddingLeft: 20 }}>{(v?.assumptions ?? []).map((f, i) => <li key={i}>{f}</li>)}</ul>
        {v?.rates.sbi_to && <p className="tiny muted" style={{ margin: 0 }}>Rupees a dollar: {v.rates.source}, from SBI's daily rate sheets ({dateOnly(v.rates.sbi_from)} to {dateOnly(v.rates.sbi_to)}); the RBI reference rate where SBI's isn't known, marked "RBI".</p>}
      </section>
    </div>
  );
}
