import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, dataUrl } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, dateOnly, money, pct, price, qty as qtyText, safeHref, signClass } from "../lib/format";
import { AsOf, Empty, Loading, Modal } from "../components/ui";
import { Trash, Upload } from "../components/Icons";
import { track } from "../lib/analytics";
import { HoldingsActionsPanel } from "../components/CorpActions";
import { SurvBadges } from "../components/Surveillance";
import { CompanyCombobox } from "../components/CompanyCombobox";

type Row = {
  symbol: string; exchange: string; name: string; sector: string; qty: number; avg: number | null; price: number | null;
  value: number | null; invested: number | null; pnl: number | null; pnl_pct: number | null; day: number | null; day_pct: number | null;
  weight: number | null; market?: "IN" | "US"; currency?: string;
  kind?: "stock" | "etf" | "reit" | "invit" | "sgb"; kind_label?: string | null;   // ETFs, REITs, InvITs and gold bonds get a badge
};
type UsTotals = { value: number; invested: number; pnl: number | null; pnl_pct: number | null; day: number | null; day_pct: number | null; count: number; in_total: boolean };
type View = {
  rows: Row[]; allocation: { sector: string; value: number; pct: number | null; count: number }[];
  totals: { value: number; invested: number; pnl: number | null; pnl_pct: number | null; day: number | null; day_pct: number | null; count: number; priced: number };
  source: string | null; updated_at: string | null; prices: boolean; prices_at?: string | null; limit: number; facts_max: number;
  us?: UsTotals | null; usd_inr?: number | null; us_prices?: boolean | null;
};
type Mkt = "IN" | "US";
type Facts = {
  stage: number | null; st_up: boolean | null; signal: string | null; red: number | null; amber: number | null; flags: string[];
  recent: { at: string; label: string; severity: string; subject: string; url: string | null }[]; results: { date: string; subject: string; url: string | null } | null;
};
type FactsReply = { rows: Record<string, Facts>; filings: boolean; filings_plan: string; checked: number; count: number };
type Unmatched = { line: number | null; text: string; reason: string };
type ImportReply = { broker: string; imported: number; saved: boolean; unmatched: Unmatched[]; unmatched_count: number; over_limit: string[]; limit: number; holdings: View };

const MAX_MB = 2;
const BROKERS = "Zerodha (Console or Kite), Groww, Upstox, Angel One, ICICI Direct and HDFC Securities";
const inr = (v: number | null | undefined) => money(v, "INR", 0);
const usd = (v: number | null | undefined) => money(v, "USD", 0);
const isUS = (r: Row) => r.market === "US";

function Trend({ f }: { f?: Facts }) {
  if (!f || f.stage == null) return <span className="muted">–</span>;
  return <>Stage {f.stage} · ST {f.st_up ? "up" : "down"}</>;
}

function FilingsCell({ f, allowed, plan }: { f?: Facts; allowed: boolean; plan?: string }) {
  if (!allowed) return <span className="muted">{plan ?? "Basic"}</span>;
  if (!f || f.red == null) return <span className="muted">–</span>;
  if (f.red) return <span>{f.red} red flag{f.red === 1 ? "" : "s"}</span>;
  return <>{f.amber ? `${f.amber} to look at` : "No red flags"}</>;
}

export function HoldingsPage() {
  const { fail, notify } = useApp();
  const [view, setView] = useState<View | null>(null);
  const [facts, setFacts] = useState<FactsReply | null>(null);
  const [mode, setMode] = useState<"replace" | "add">("replace");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportReply | null>(null);
  const [edit, setEdit] = useState<Row | null>(null);
  const [add, setAdd] = useState<{ symbol: string; qty: string; avg: string; market: Mkt }>({ symbol: "", qty: "", avg: "", market: "IN" });
  const file = useRef<HTMLInputElement>(null);

  const loadFacts = useCallback((v: View) => {
    setFacts(null);
    if (v.rows.length) api<FactsReply>("/holdings/facts").then(setFacts).catch(() => setFacts({ rows: {}, filings: true, filings_plan: "Basic", checked: 0, count: 0 }));
  }, []);
  const [actionsAt, setActionsAt] = useState(0);         // reload the corporate actions whenever the holdings change
  const show = useCallback((v: View) => { setView(v); loadFacts(v); setActionsAt((n) => n + 1); }, [loadFacts]);
  useEffect(() => { api<View>("/holdings").then(show).catch(fail); }, [show, fail]);

  const pick = async (f: File | undefined) => {
    if (!f) return;
    if (f.size > MAX_MB * 1024 * 1024) { notify(`That file is larger than ${MAX_MB} MB. A holdings export is much smaller; check it's the right file.`); return; }
    setBusy(true);
    try {
      const data = await dataUrl(f);
      const r = await api<ImportReply>("/holdings/import", { method: "POST", body: { filename: f.name, data, mode } });
      track("holdings imported", { rows: r.imported, method: mode });
      setResult(r);
      show(r.holdings);
    } catch (e) { fail(e); } finally {
      setBusy(false);
      if (file.current) file.current.value = "";
    }
  };

  const save = async (items: { symbol: string; qty: number; avg: number | null; market: Mkt }[], done?: string) => {
    setBusy(true);
    try {
      const r = await api<{ unmatched: Unmatched[]; holdings: View }>("/holdings", { method: "PUT", body: { items } });
      show(r.holdings);
      if (r.unmatched.length) notify(`${r.unmatched.map((u) => u.text).join(", ")}: ${r.unmatched[0].reason.startsWith("No US") ? "no US-listed company has that ticker" : "no listed company on NSE or BSE has that symbol"}.`);
      else if (done) notify(done);
      return !r.unmatched.length;
    } catch (e) { fail(e); return false; } finally { setBusy(false); }
  };
  const current = () => (view?.rows ?? []).map((r) => ({ symbol: r.symbol, qty: r.qty, avg: r.avg, market: (r.market ?? "IN") as Mkt }));
  const same = (x: { symbol: string; market: Mkt }, r: Row) => x.symbol === r.symbol && x.market === (r.market ?? "IN");

  const addOne = async () => {
    const q = Number(add.qty), a = add.avg.trim() ? Number(add.avg) : null;
    if (!add.symbol.trim() || !(q > 0) || (a != null && !(a >= 0))) { notify("Enter the symbol, a quantity above 0 and, if you like, the average price."); return; }
    if (await save([...current(), { symbol: add.symbol.trim(), qty: q, avg: a, market: add.market }], `${add.symbol.trim().toUpperCase()} added.`)) setAdd({ symbol: "", qty: "", avg: "", market: add.market });
  };

  const remove = () => {
    if (!confirm("Delete my holdings? Every saved position is removed from StratLab. Your broker account isn't touched.")) return;
    api("/holdings", { method: "DELETE" }).then(() => {
      setResult(null); setFacts(null);
      return api<View>("/holdings").then(setView);
    }).then(() => notify("Your holdings are deleted.")).catch(fail);
  };

  const rows = view?.rows ?? [];
  const t = view?.totals;
  const withFilings = facts ? rows.filter((r) => (facts.rows[r.symbol]?.recent.length ?? 0) > 0) : [];

  return (
    <div className="stack" style={{ gap: 24 }}>
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">My Holdings</span>
        <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.1 }}>Your stocks, at today's prices</h1>
        <p className="muted" style={{ fontSize: 17, maxWidth: 760 }}>Upload the holdings file from your broker to see what each position is worth, its gain or loss, today's change, your mix by sector, and what each company has filed. Facts only, not advice. Only you can see your holdings, and you can delete them at any time.</p>
      </div>

      <section className="card stack" style={{ gap: 14 }}>
        <div className="stack" style={{ gap: 4 }}>
          <h2 className="h2">Import from your broker</h2>
          <p className="small muted" style={{ margin: 0 }}>Download your holdings as Excel or CSV from {BROKERS} (usually Portfolio › Holdings › Download), then upload it here. Any other CSV works too with columns for Symbol (or ISIN), Quantity and Average price.</p>
        </div>
        <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <label className={`btn${busy ? " disabled" : ""}`} style={{ cursor: busy ? "wait" : "pointer" }}>
            <Upload size={18} />{busy ? "Reading…" : "Upload holdings file"}
            <input ref={file} type="file" accept=".csv,.xlsx,.xls,.txt,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden disabled={busy}
              onChange={(e) => pick(e.target.files?.[0])} aria-label="Holdings file" />
          </label>
          {rows.length > 0 && (
            <div className="seg" role="radiogroup" aria-label="What the file does">
              <button role="radio" aria-checked={mode === "replace"} aria-pressed={mode === "replace"} onClick={() => setMode("replace")}>Replace my holdings</button>
              <button role="radio" aria-checked={mode === "add"} aria-pressed={mode === "add"} onClick={() => setMode("add")}>Add to them</button>
            </div>
          )}
        </div>
        {result && (
          <div className="stack" style={{ gap: 8 }} role="status">
            <p className="small" style={{ margin: 0 }}>
              <b>{result.broker === "CSV" ? "Read as a CSV file" : `Read as a ${result.broker} file`}:</b>{" "}
              {result.saved ? `${result.imported} stock${result.imported === 1 ? "" : "s"} saved.` : "nothing matched, so your saved holdings are unchanged."}
              {result.unmatched_count > 0 && ` ${result.unmatched_count} line${result.unmatched_count === 1 ? "" : "s"} couldn't be matched (below).`}
            </p>
            {result.over_limit.length > 0 && (
              <p className="small" style={{ margin: 0 }}>Your plan keeps {result.limit} stocks, so {result.over_limit.length} were left out: {result.over_limit.slice(0, 12).join(", ")}{result.over_limit.length > 12 ? "…" : ""}. <Link className="link" to="/plans">See plans</Link></p>
            )}
            {result.unmatched.length > 0 && (
              <div className="table-wrap" style={{ margin: 0 }}>
                <table aria-label="Lines that couldn't be matched">
                  <thead><tr><th>Line</th><th>What the file says</th><th style={{ textAlign: "left" }}>Why</th></tr></thead>
                  <tbody>
                    {result.unmatched.map((u, i) => (
                      <tr key={i}><td className="num">{u.line ?? "–"}</td><td>{u.text || "–"}</td><td style={{ textAlign: "left", whiteSpace: "normal" }} className="small muted">{u.reason}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {result.unmatched.length > 0 && <p className="tiny muted" style={{ margin: 0 }}>Add any of these by hand below with its NSE symbol or BSE code.</p>}
          </div>
        )}
      </section>

      {!view && <Loading label="Opening your holdings" />}
      {view && rows.length === 0 && (
        <Empty title="No holdings yet">
          <p className="muted" style={{ maxWidth: 520 }}>Upload your broker's holdings file above, or add stocks one at a time below.</p>
        </Empty>
      )}

      {view && t && rows.length > 0 && (
        <>
          <div className="stat-row">
            <div className="stat"><span className="tiny muted">Current value</span><b className="num">{inr(t.value)}</b></div>
            <div className="stat"><span className="tiny muted">Invested</span><b className="num">{inr(t.invested)}</b></div>
            <div className="stat"><span className="tiny muted">Unrealised P&amp;L</span><b className={`num ${signClass(t.pnl)}`}>{t.pnl == null ? "–" : `${inr(t.pnl)} (${pct(t.pnl_pct)})`}</b></div>
            <div className="stat"><span className="tiny muted">Today</span><b className={`num ${signClass(t.day)}`}>{t.day == null ? "–" : `${inr(t.day)} (${pct(t.day_pct, 2)})`}</b></div>
          </div>
          <p className="tiny muted" style={{ margin: "-12px 0 0" }}>
            {t.count} stock{t.count === 1 ? "" : "s"}{view.source ? ` · from ${view.source === "Manual" ? "your own entries" : view.source === "CSV" ? "a CSV file" : `your ${view.source} file`}` : ""}{view.updated_at ? ` · updated ${ago(view.updated_at)}` : ""}
            {!view.prices && " · Live prices are offline right now, so values are shown at cost."}
          </p>
          {view.us && (
            <p className="small" style={{ margin: 0 }} aria-label="US stocks">
              <b>US stocks</b> ({view.us.count}): {usd(view.us.value)} · invested {usd(view.us.invested)}
              {view.us.pnl != null && <> · <span className={signClass(view.us.pnl)}>{usd(view.us.pnl)} ({pct(view.us.pnl_pct)})</span></>}
              <span className="tiny muted"> · {view.us.in_total && view.usd_inr ? `in the rupee totals above at ₹${view.usd_inr.toFixed(2)} a dollar` : "not in the rupee totals above: the exchange rate isn't available right now"}
                {view.us_prices === false && " · US prices are offline right now, so these are at cost"}. US stocks aren't part of the tax report, which works out Indian capital gains.</span>
            </p>
          )}
          <AsOf parts={[["Prices", view.prices_at]]} />
          <HoldingsActionsPanel<View> version={actionsAt} onHoldings={setView} />

          <section className="card stack" style={{ gap: 12 }}>
            <h2 className="h2">By sector</h2>
            <div className="stack" style={{ gap: 10 }}>
              {view.allocation.map((a) => (
                <div key={a.sector} className="seg-row">
                  <div className="spread small" style={{ gap: 10 }}><span>{a.sector} <span className="muted tiny">· {a.count} stock{a.count === 1 ? "" : "s"}</span></span><span className="num">{a.pct == null ? "–" : `${a.pct.toFixed(1)}%`}</span></div>
                  <div className="seg-bar"><i style={{ width: `${Math.max(1, Math.min(100, a.pct ?? 0))}%` }} /></div>
                </div>
              ))}
            </div>
            <p className="tiny muted" style={{ margin: 0 }}>Share of the current value, by the exchange's sector for each company.</p>
          </section>

          <section className="card stack" style={{ gap: 12 }}>
            <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
              <h2 className="h2">Positions</h2>
              {!facts && <span className="tiny muted">Checking each stock's trend and filings…</span>}
            </div>
            <div className="table-wrap">
              <table aria-label="Positions">
                <thead>
                  <tr><th>Stock</th><th>Sector</th><th>Qty</th><th>Avg. price</th><th>Price</th><th>Value</th><th>Unrealised P&amp;L</th><th>Today</th><th>Weight</th>
                    <th style={{ textAlign: "left" }}>Trend</th><th style={{ textAlign: "left" }}>Filings, 3 months</th><th style={{ textAlign: "left" }}>Results meeting</th><th /></tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const f = facts?.rows[r.symbol];
                    return (
                      <tr key={`${r.exchange}:${r.symbol}`}>
                        <td>{r.kind && r.kind !== "stock" ? <b>{r.symbol}</b> : <Link className="link" to={`/research/${isUS(r) ? "US" : "IN"}/${encodeURIComponent(r.symbol)}`}><b>{r.symbol}</b></Link>}{r.exchange === "BSE" && <span className="tiny muted"> BSE</span>}{isUS(r) && <span className="tiny muted"> US</span>}{r.kind_label && <> <span className={`badge kind-${r.kind}`} title="Instrument type">{r.kind_label}</span></>}<div className="tiny muted" style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>{r.name}</div>{!isUS(r) && (!r.kind || r.kind === "stock") && <SurvBadges region="IN" symbol={r.symbol} />}</td>
                        <td className="small">{r.sector}</td>
                        <td className="num">{qtyText(r.qty)}</td>
                        <td className="num">{price(r.avg, r.currency ?? "INR")}</td>
                        <td className="num">{price(r.price, r.currency ?? "INR")}</td>
                        <td className="num">{money(r.value ?? r.invested, r.currency ?? "INR", 0)}</td>
                        <td className={`num ${signClass(r.pnl)}`}>{r.pnl == null ? "–" : <>{money(r.pnl, r.currency ?? "INR", 0)} <span className="tiny">{pct(r.pnl_pct)}</span></>}</td>
                        <td className={`num ${signClass(r.day)}`}>{r.day == null ? "–" : <>{money(r.day, r.currency ?? "INR", 0)} <span className="tiny">{pct(r.day_pct, 2)}</span></>}</td>
                        <td className="num">{r.weight == null ? "–" : `${r.weight.toFixed(1)}%`}</td>
                        <td style={{ textAlign: "left" }} className="small"><Trend f={f} /></td>
                        <td style={{ textAlign: "left" }} className="small"><FilingsCell f={f} allowed={facts?.filings !== false} plan={facts?.filings_plan} /></td>
                        <td style={{ textAlign: "left" }} className="small">{f?.results ? <a className="link" href={safeHref(f.results.url)} target="_blank" rel="noreferrer">{dateOnly(f.results.date)}</a> : <span className="muted">–</span>}</td>
                        <td><button className="btn quiet sm" onClick={() => setEdit(r)} aria-label={`Edit ${r.symbol}`}>Edit</button></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
          {facts && facts.count > facts.checked && <p className="tiny muted" style={{ margin: "-12px 0 0" }}>Trend and filings are shown for the {facts.checked} largest positions.</p>}
          {facts && !facts.filings && (
            <div className="banner"><span>Red flags, recent filings and results dates come from the filings feature on the {facts.filings_plan} plan.</span><Link to="/plans" className="btn sm">See plans</Link></div>
          )}

          {withFilings.length > 0 && (
            <section className="card stack" style={{ gap: 12 }}>
              <h2 className="h2">Recent filings</h2>
              <div className="stack" style={{ gap: 14 }}>
                {withFilings.map((r) => {
                  const f = facts!.rows[r.symbol];
                  return (
                    <div key={r.symbol} className="stack" style={{ gap: 6 }}>
                      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}><b>{r.symbol}</b>{f.flags.length > 0 && <span className="tiny muted">Last 3 months: {f.flags.join(" · ")}</span>}</div>
                      {f.recent.map((x, i) => (
                        <div key={i} className="small" style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "baseline" }}>
                          <span className="mono tiny muted">{dateOnly(x.at)}</span>
                          <span className="badge fact">{x.label}</span>
                          {x.url ? <a className="link" href={safeHref(x.url)} target="_blank" rel="noreferrer" style={{ minWidth: 0, overflowWrap: "anywhere" }}>{x.subject || "Filing"}</a> : <span style={{ minWidth: 0, overflowWrap: "anywhere" }}>{x.subject}</span>}
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
              <p className="tiny muted" style={{ margin: 0 }}>From the companies' own exchange filings, sorted by fixed rules you can read on the <Link className="link" to="/research/filings">Red flags</Link> page.</p>
            </section>
          )}
        </>
      )}

      {view && (
        <section className="card stack" style={{ gap: 12 }}>
          <h2 className="h2">Add a stock by hand</h2>
          <div className="seg" role="radiogroup" aria-label="Where it's listed" style={{ alignSelf: "flex-start" }}>
            {(["IN", "US"] as Mkt[]).map((m) => (
              <button key={m} role="radio" aria-checked={add.market === m} aria-pressed={add.market === m}
                onClick={() => setAdd({ ...add, market: m, symbol: add.market === m ? add.symbol : "" })}>{m === "IN" ? "India (NSE/BSE)" : "United States"}</button>
            ))}
          </div>
          <div className="holdings-add">
            <CompanyCombobox label={add.market === "IN" ? "NSE symbol or BSE code" : "US ticker"} market={add.market} value={add.symbol}
              placeholder={add.market === "IN" ? "Name or symbol, e.g. Reliance" : "Name or ticker, e.g. Apple"}
              onChange={(t) => setAdd((x) => ({ ...x, symbol: t }))} onPick={(s) => setAdd((x) => ({ ...x, symbol: s.id, market: s.market }))} onEnter={addOne} />
            <label className="field">Quantity<input value={add.qty} inputMode="decimal" placeholder="10" onChange={(e) => setAdd({ ...add, qty: e.target.value })} /></label>
            <label className="field">Average price ({add.market === "US" ? "$" : "₹"}, optional)<input value={add.avg} inputMode="decimal" placeholder={add.market === "US" ? "180" : "2,450"} onChange={(e) => setAdd({ ...add, avg: e.target.value.replace(/,/g, "") })} /></label>
            <button className="btn" disabled={busy} onClick={addOne}>Add</button>
          </div>
          {add.market === "US" && <p className="tiny muted" style={{ margin: 0 }}>US stocks are valued in dollars, and added to your totals in rupees at the day's exchange rate. They aren't part of the tax report.</p>}
        </section>
      )}

      {view && rows.length > 0 && (
        <section className="stack" style={{ gap: 8 }}>
          <p className="small muted" style={{ margin: 0, maxWidth: "80ch" }}>Your holdings are stored with your account only, used for this page and your My Stocks newsletter, and never shared. Values use the latest prices; P&amp;L is before charges and taxes. Nothing here is investment advice.</p>
          <button className="btn danger" style={{ alignSelf: "flex-start" }} onClick={remove}><Trash size={16} />Delete my holdings</button>
        </section>
      )}

      {edit && (
        <EditHolding row={edit} busy={busy} onClose={() => setEdit(null)}
          onSave={async (q, a) => { if (await save(current().map((x) => (same(x, edit) ? { ...x, qty: q, avg: a } : x)), `${edit.symbol} updated.`)) setEdit(null); }}
          onRemove={async () => { if (await save(current().filter((x) => !same(x, edit)), `${edit.symbol} removed.`)) setEdit(null); }} />
      )}
    </div>
  );
}

function EditHolding({ row, busy, onClose, onSave, onRemove }: { row: Row; busy: boolean; onClose: () => void; onSave: (qty: number, avg: number | null) => void; onRemove: () => void }) {
  const [q, setQ] = useState(String(row.qty));
  const [a, setA] = useState(row.avg == null ? "" : String(row.avg));
  const qn = Number(q), an = a.trim() ? Number(a) : null;
  const ok = qn > 0 && (an == null || an >= 0);
  return (
    <Modal title={`Edit ${row.symbol}`} onClose={onClose}>
      <div className="stack" style={{ gap: 14 }}>
        <label className="field">Quantity<input value={q} inputMode="decimal" onChange={(e) => setQ(e.target.value)} /></label>
        <label className="field">Average price ({row.market === "US" ? "$" : "₹"}, optional)<input value={a} inputMode="decimal" onChange={(e) => setA(e.target.value.replace(/,/g, ""))} /></label>
        <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
          <button className="btn" disabled={busy || !ok} onClick={() => onSave(qn, an)}>Save</button>
          <button className="btn danger" disabled={busy} onClick={onRemove}><Trash size={16} />Remove from holdings</button>
        </div>
      </div>
    </Modal>
  );
}
