import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { dateOnly, money, qty as qtyText, signClass } from "../../lib/format";
import { AsOf, Empty, Info, Loading } from "../../components/ui";
import { Trash, Upload } from "../../components/Icons";
import { track } from "../../lib/analytics";

// ---------- what the server sends ----------
type Company = {
  symbol: string; name: string; country: "IN" | "US"; count: number; amount: number; amount_usd: number | null; tds_file: number | null;
  first: string; last: string; tds_expected?: number; over_threshold?: boolean; withheld_usd?: number; withheld?: number;
};
type DivYear = {
  fy: number; label: string; total: number; india_total: number; us_total: number; count: number; companies_count: number; unpriced: number; taxed: boolean;
  tds: { threshold: number | null; rate: number; section: string; expected: number; companies_over: number; in_file: number | null };
  us: { gross_usd: number; gross: number; rate: number; withheld_usd: number; withheld: number } | null;
  companies: Company[]; locked: boolean; source: "files" | "estimated" | "none"; include: boolean; include_saved: boolean; estimate_total: number | null;
};
type Dividends = {
  years: DivYear[]; current_fy: number; files: { name: string; source: string; rows: number; at: string }[]; updated_at: string | null;
  ahead: { symbol: string; ex_date: string; label: string | null; qty: number; per_share: number; currency: string; amount: number }[];
  ahead_total: number; usd_inr: number | null; as_of: string; assumptions: string[]; locked: boolean;
};
type DueDate = { n: number; date: string; pct: number; label: string };
type Instalment = DueDate & {
  base: number; required: number; paid: number; short: number; to_pay: number; interest_234c: number; interest_if_missed: number; months: number;
  tolerated: boolean; status: "passed" | "next" | "later";
};
type Schedule = {
  fy: number; label: string; tax: number; tds: number; net: number; due: boolean; threshold: number; instalments: Instalment[]; next: number | null; paid: number;
  interest_234c: number; b234: { applies: boolean; paid: number; ninety_pct: number; short: number; months: number; until: string; interest: number }; steps: string[];
};
type Payment = { d: string; amount: number };
type Advance = {
  fy: number; label: string; dates: DueDate[]; remind: boolean; locked: boolean; as_of: string; assumptions: string[]; threshold: number; current_fy: number;
  schedule?: Schedule; inputs?: { tds: number; paid: Payment[] }; dividends_in_estimate?: number; dividend_tds?: number; income_saved?: boolean;
};
type LtLot = { key: string; bought: string; qty: number; cost: number; price: number; value: number; gain: number; grandfathered: boolean; bonus: boolean; text: string };
type SoonLot = LtLot & { long_from: string; days_left: number; window: number };
type BelowLot = { key: string; bought: string; qty: number; cost: number; price: number; value: number; loss: number; loss_pct: number | null; days: number; term: "ST" | "LT"; long_from: string | null };
type Ltcg = {
  fy: number; label: string; as_of: string; exemption: { limit: number; used: number; left: number; realised_lt_net: number; realised_st_net: number };
  open_lt: { lots: number; gains: number; losses: number; with_gain: number }; soon_counts: Record<string, number>; long: LtLot[]; soon: SoonLot[];
  unpriced: number; facts: string[]; locked: boolean; below_cost: { rows: BelowLot[]; unpriced: number; open: number; st: number; lt: number };
  names: Record<string, { symbol: string }>; prices: boolean; trades: number;
};

const inr = (v: number | null | undefined) => money(v, "INR", 0);
const usd = (v: number | null | undefined) => money(v, "USD", 2);
const TABS = [["dividends", "Dividends"], ["advance", "Advance tax"], ["ltcg", "Long-term exemption"]] as const;
type Tab = (typeof TABS)[number][0];
const DISCLAIMER = "Estimates and arithmetic on your own figures, not tax advice. Check them with a chartered accountant (CA) before you file or pay tax.";

function Locked({ text }: { text: string }) {
  return (
    <div className="banner" role="note">
      <span>{text} <Link className="link" to="/plans">See plans</Link></span>
    </div>
  );
}

export function TaxToolsPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find(([t]) => t === params.get("tab"))?.[0]) ?? "dividends";
  const go = (t: Tab) => setParams((p) => { const n = new URLSearchParams(p); n.set("tab", t); return n; }, { replace: true });
  return (
    <div className="stack" style={{ gap: 24 }}>
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Money · Tax tools</span>
        <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.1 }}>Dividends, advance tax and the long-term exemption</h1>
        <p className="muted" style={{ fontSize: 17, maxWidth: 760 }}>Built on your <Link className="link" to="/tax-report">tax report</Link> and <Link className="link" to="/holdings">holdings</Link>: the dividends you received and the TDS on them, the advance tax due by each date, and how much of this year's long-term gains exemption is used. Only you can see these figures.</p>
      </div>
      <div className="banner tax-note" role="note"><span><b>Estimate only.</b> {DISCLAIMER}</span></div>
      <div className="seg" role="tablist" aria-label="Tax tools" style={{ alignSelf: "flex-start" }}>
        {TABS.map(([t, label]) => <button key={t} role="tab" aria-selected={tab === t} aria-pressed={tab === t} onClick={() => go(t)}>{label}</button>)}
      </div>
      {tab === "dividends" && <DividendsTab />}
      {tab === "advance" && <AdvanceTab />}
      {tab === "ltcg" && <LtcgTab />}
    </div>
  );
}

// ---------- dividends ----------
function DividendsTab() {
  const { fail, notify } = useApp();
  const [v, setV] = useState<Dividends | null>(null);
  const [fy, setFy] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const show = useCallback((d: Dividends) => {
    setV(d);
    setFy((cur) => cur ?? (d.years.find((y) => y.fy === d.current_fy && y.total > 0) ?? d.years.find((y) => y.total > 0) ?? d.years[0])?.fy ?? d.current_fy);
  }, []);
  useEffect(() => { api<Dividends>("/money/dividends").then(show).catch(fail); }, [show, fail]);

  const pick = async (files: FileList | null) => {
    const f = files?.[0];
    if (!f) return;
    if (f.size > 10 * 1024 * 1024) { notify("That file is larger than 10 MB."); return; }
    setBusy(true);
    try {
      const r = await api<{ read: number; added: number; duplicates: number; problems: { line: number; text: string; reason: string }[]; dividends: Dividends }>(
        `/money/dividends/import?${new URLSearchParams({ filename: f.name.slice(0, 200) })}`, { method: "POST", file: f });
      setNote(`${r.added} dividend${r.added === 1 ? "" : "s"} added${r.duplicates ? `, ${r.duplicates} already there (skipped)` : ""}${r.problems.length ? `, ${r.problems.length} line${r.problems.length === 1 ? "" : "s"} left out` : ""}.`);
      setFy(null);
      show(r.dividends);
      track("dividends imported", { rows: r.added });
    } catch (e) { fail(e); } finally { setBusy(false); if (file.current) file.current.value = ""; }
  };
  const include = async (year: number, on: boolean) => {
    try { show(await api<Dividends>("/money/dividends/include", { method: "PUT", body: { fy: year, include: on } })); notify(on ? "Included in the total tax estimate." : "Left out of the total tax estimate."); }
    catch (e) { fail(e); }
  };
  const remove = async () => {
    if (!confirm("Delete the dividends you uploaded? The estimate from your holdings stays, as it is worked out each time.")) return;
    try { await api("/money/dividends", { method: "DELETE" }); setNote(null); setFy(null); show(await api<Dividends>("/money/dividends")); notify("Your uploaded dividends are deleted."); }
    catch (e) { fail(e); }
  };

  if (!v) return <Loading label="Adding up your dividends" />;
  const y = v.years.find((x) => x.fy === fy) ?? v.years[0];
  return (
    <div className="stack" style={{ gap: 20 }}>
      <section className="card stack" style={{ gap: 12 }}>
        <div className="stack" style={{ gap: 4 }}>
          <h2 className="h2">Your dividends</h2>
          <p className="small muted" style={{ margin: 0 }}>Upload your broker's dividend statement as CSV or Excel, with columns for the date, the company (symbol, name or ISIN) and the amount (or quantity and dividend a share); TDS and currency are optional (USD for US dividends). A Zerodha tax P&amp;L ZIP uploaded to the tax report brings its dividend sheet too. Without a file, the year is estimated from your holdings and the dividends the companies declared.</p>
        </div>
        <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <label className={`btn${busy ? " disabled" : ""}`} style={{ cursor: busy ? "wait" : "pointer" }}>
            <Upload size={18} />{busy ? "Reading…" : "Upload dividends"}
            <input ref={file} type="file" accept=".csv,.xlsx,.txt,.zip,text/csv" hidden disabled={busy} onChange={(e) => pick(e.target.files)} aria-label="Dividend file" />
          </label>
          {v.files.length > 0 && <button className="btn quiet sm" onClick={remove}><Trash size={16} />Delete uploaded dividends</button>}
        </div>
        {note && <p className="small" role="status" style={{ margin: 0 }}>{note}</p>}
        {v.files.length > 0 && <p className="tiny muted" style={{ margin: 0 }}>From {v.files.map((f) => f.name).join(", ")}.</p>}
      </section>

      {y && (
        <>
          <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "flex-end", justifyContent: "space-between" }}>
            <label className="field" style={{ minWidth: 200 }}>Financial year
              <select value={y.fy} onChange={(e) => setFy(Number(e.target.value))} aria-label="Financial year">
                {v.years.map((x) => <option key={x.fy} value={x.fy}>{x.label}{x.fy === v.current_fy ? " (this year)" : ""}</option>)}
              </select>
            </label>
            {y.source !== "none" && y.taxed && (
              <div className="seg" role="radiogroup" aria-label="In the total tax estimate">
                <button role="radio" aria-checked={y.include} aria-pressed={y.include} onClick={() => include(y.fy, true)}>Include in the tax estimate</button>
                <button role="radio" aria-checked={!y.include} aria-pressed={!y.include} onClick={() => include(y.fy, false)}>Leave out</button>
              </div>
            )}
          </div>
          <section className="card stack" style={{ gap: 14 }} aria-label="Dividends for the year">
            <div className="row" style={{ gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
              <h2 className="h2">Dividends, {y.label}</h2>
              {y.source === "files" && <span className="badge">From your files</span>}
              {y.source === "estimated" && <span className="badge">Estimated</span>}
            </div>
            {y.source === "none" ? <p className="small muted" style={{ margin: 0 }}>No dividends in your files or holdings for {y.label}.</p> : (
              <>
                <div className="stat-row">
                  <div className="stat"><span className="tiny muted">Dividend income</span><b className="num" aria-label="Dividend income">{inr(y.total)}</b>
                    <span className="tiny muted">{y.count} payment{y.count === 1 ? "" : "s"} from {y.companies_count} compan{y.companies_count === 1 ? "y" : "ies"}</span></div>
                  <div className="stat"><span className="tiny muted">Indian companies</span><b className="num">{inr(y.india_total)}</b>
                    <span className="tiny muted">{y.tds.threshold != null ? `TDS above ${inr(y.tds.threshold)} a company` : "Exempt that year"}</span></div>
                  {!y.locked && y.tds.threshold != null && (
                    <div className="stat"><span className="tiny muted">TDS expected <Info label="About TDS on dividends">A company cuts 10% TDS (20% without a PAN) from a resident once its dividends to you in the year are over the threshold, on the whole amount: {inr(y.tds.threshold)} for {y.label} under {y.tds.section}. Form 26AS or the AIS shows what was actually cut.</Info></span>
                      <b className="num">{inr(y.tds.expected)}</b><span className="tiny muted">{y.tds.companies_over} compan{y.tds.companies_over === 1 ? "y" : "ies"} over the threshold{y.tds.in_file != null ? ` · ${inr(y.tds.in_file)} in your file` : ""}</span></div>
                  )}
                  {!y.locked && y.us && (
                    <div className="stat"><span className="tiny muted">US dividends <Info label="About US dividends">The US withholds 25% under the India-US tax treaty (with a W-8BEN). In India the dividend is taxed at your slab rate, and the US tax can be claimed as a foreign tax credit, up to the Indian tax on that income, by filing Form 67 before the return.</Info></span>
                      <b className="num">{inr(y.us.gross)}</b><span className="tiny muted">{usd(y.us.gross_usd)} · US tax withheld {usd(y.us.withheld_usd)} ({inr(y.us.withheld)}), the foreign tax credit figure</span></div>
                  )}
                </div>
                <p className="small" style={{ margin: 0 }}>{y.taxed ? (y.include
                  ? <>Included in the <Link className="link" to="/tax-report">total tax estimate</Link> as income from other sources, taxed at your slab rate.</>
                  : <>Not in the <Link className="link" to="/tax-report">total tax estimate</Link>{y.source === "estimated" ? " (an estimate is left out until you include it)" : ""}.</>)
                  : "Dividends were exempt in your hands before FY 2020-21 (the company paid dividend distribution tax)."}</p>
                {y.source === "files" && y.estimate_total != null && <p className="tiny muted" style={{ margin: 0 }}>From your holdings, the estimate for {y.label} is {inr(y.estimate_total)}.</p>}
                {y.unpriced > 0 && <p className="tiny muted" style={{ margin: 0 }}>{y.unpriced} US payment{y.unpriced === 1 ? " isn't" : "s aren't"} counted: the dollar rate isn't available right now.</p>}
                {y.locked ? <Locked text="Dividends by company, with the TDS expected and the US tax withheld, are on the Basic plan." /> : y.companies.length > 0 && (
                  <div className="table-wrap">
                    <table aria-label="Dividends by company">
                      <thead><tr><th style={{ textAlign: "left" }}>Company</th><th>Payments</th><th>Amount</th><th>TDS expected</th><th>US tax withheld</th></tr></thead>
                      <tbody>{y.companies.map((c) => (
                        <tr key={`${c.country}${c.symbol}`}>
                          <td style={{ textAlign: "left" }}><b>{c.symbol}</b>{c.country === "US" && <span className="tiny muted"> US</span>}</td>
                          <td className="num">{c.count}</td>
                          <td className="num">{inr(c.amount)}{c.amount_usd != null && <div className="tiny muted">{usd(c.amount_usd)}</div>}</td>
                          <td className="num">{c.country === "IN" ? inr(c.tds_expected) : "–"}</td>
                          <td className="num">{c.country === "US" ? usd(c.withheld_usd) : "–"}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </section>
        </>
      )}

      {v.ahead.length > 0 && (
        <section className="card stack" style={{ gap: 10 }}>
          <h2 className="h2">Declared, ex-date still ahead</h2>
          <p className="small muted" style={{ margin: 0 }}>{inr(v.ahead_total)} at the shares you hold now. Not counted above until paid.</p>
          <ul className="small" style={{ margin: 0, paddingLeft: 20 }}>
            {v.ahead.map((a, i) => <li key={i}><b>{a.symbol}</b> {a.label ?? "Dividend"}, ex-date {dateOnly(a.ex_date)}: {qtyText(a.qty)} × {money(a.per_share, a.currency === "USD" ? "USD" : "INR", 2)} = {money(a.amount, a.currency === "USD" ? "USD" : "INR", 0)}</li>)}
          </ul>
        </section>
      )}

      <section className="card stack" style={{ gap: 8 }}>
        <h2 className="h2">How these are worked out</h2>
        <ul className="small muted" style={{ margin: 0, paddingLeft: 20 }}>{v.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
        <AsOf parts={[["Dividends", v.as_of]]} />
      </section>
    </div>
  );
}

// ---------- advance tax ----------
const num = (s: string) => { const n = Number(s.replace(/[,\s₹]/g, "")); return s.trim() === "" ? 0 : Number.isFinite(n) && n >= 0 ? n : NaN; };

function AdvanceTab() {
  const { fail, notify } = useApp();
  const [v, setV] = useState<Advance | null>(null);
  const [fy, setFy] = useState<number | null>(null);
  useEffect(() => { api<Advance>(`/money/advance-tax${fy ? `?fy=${fy}` : ""}`).then(setV).catch(fail); }, [fy, fail]);
  const remind = async (on: boolean) => {
    try { await api("/money/advance-tax/reminders", { method: "PUT", body: { on } }); setV((x) => (x ? { ...x, remind: on } : x)); notify(on ? "Reminders on: 7 days and 1 day before each date." : "Reminders off."); }
    catch (e) { fail(e); }
  };
  if (!v) return <Loading label="Working out the instalments" />;
  const s = v.schedule;
  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "flex-end", justifyContent: "space-between" }}>
        <label className="field" style={{ minWidth: 200 }}>Financial year
          <select value={v.fy} onChange={(e) => setFy(Number(e.target.value))} aria-label="Financial year">
            {[v.current_fy, v.current_fy - 1].map((x) => <option key={x} value={x}>FY {x}-{String(x + 1).slice(2)}{x === v.current_fy ? " (this year)" : ""}</option>)}
          </select>
        </label>
        <div className="stack" style={{ gap: 6 }}>
          <span className="small muted" style={{ fontWeight: 600 }}>Reminders by email and phone <Info label="About the reminders">7 days and 1 day before each due date, to your confirmed email address and any phone notifications you set up in Account. Dates only: no amounts are sent.</Info></span>
          <div className="seg" role="radiogroup" aria-label="Advance tax reminders">
            <button role="radio" aria-checked={v.remind} aria-pressed={v.remind} onClick={() => remind(true)}>On</button>
            <button role="radio" aria-checked={!v.remind} aria-pressed={!v.remind} onClick={() => remind(false)}>Off</button>
          </div>
        </div>
      </div>

      <section className="card stack" style={{ gap: 12 }} aria-label="Advance tax due dates">
        <h2 className="h2">Due dates, {v.label}</h2>
        <ul className="due-list" style={{ margin: 0, paddingLeft: 20 }} aria-label="Due dates">
          {v.dates.map((d) => <li key={d.n} className="small"><b>{d.label}</b>: {d.pct * 100}% of the year's tax (less TDS), counting what was paid before</li>)}
        </ul>
        <p className="tiny muted" style={{ margin: 0 }}>Advance tax is due when the year's tax less TDS is {inr(v.threshold)} or more (section 208; section 404 of the Income-tax Act, 2025 from FY 2026-27).</p>
        {v.locked && <Locked text="The amounts due by each date, and the interest on a short instalment, are on the Pro plan." />}
      </section>

      {s && v.inputs && (
        <>
          <section className="card stack" style={{ gap: 14 }} aria-label="Advance tax amounts">
            <div className="stat-row">
              <div className="stat"><span className="tiny muted">Tax for the year (estimate)</span><b className="num" aria-label="Tax for the year">{inr(s.tax)}</b>
                <span className="tiny muted">from the <Link className="link" to="/tax-report">tax report</Link>{v.income_saved ? "" : ", no other income entered"}{v.dividends_in_estimate ? ` · ${inr(v.dividends_in_estimate)} of dividends in it` : ""}</span></div>
              <div className="stat"><span className="tiny muted">Less TDS</span><b className="num">{inr(s.tds)}</b><span className="tiny muted">as you entered it</span></div>
              <div className="stat"><span className="tiny muted">Advance tax for the year</span><b className="num" aria-label="Advance tax for the year">{s.due ? inr(s.net) : "None due"}</b>
                <span className="tiny muted">{s.due ? `${inr(s.paid)} paid so far` : `below ${inr(s.threshold)}`}</span></div>
              {s.due && <div className="stat"><span className="tiny muted">Interest so far (234C)</span><b className={`num ${s.interest_234c > 0 ? "neg" : ""}`}>{inr(s.interest_234c)}</b><span className="tiny muted">on instalments already due</span></div>}
            </div>
            {s.due && (
              <div className="table-wrap">
                <table aria-label="Instalments">
                  <thead><tr><th style={{ textAlign: "left" }}>By</th><th>Share</th><th>Due by then</th><th>Paid by then</th><th>Short</th><th>234C interest</th></tr></thead>
                  <tbody>{s.instalments.map((r) => (
                    <tr key={r.n}>
                      <td style={{ textAlign: "left" }}><b>{r.label}</b>{r.status === "next" && <span className="tiny muted"> next</span>}</td>
                      <td className="num">{Math.round(r.pct * 100)}%</td>
                      <td className="num">{inr(r.required)}</td>
                      <td className="num">{inr(r.paid)}</td>
                      <td className={`num ${r.short > 0 ? "neg" : ""}`}>{r.short > 0 ? inr(r.short) : "–"}{r.tolerated && <div className="tiny muted">within {r.n === 0 ? "12%" : "36%"}</div>}</td>
                      <td className="num">{r.status === "passed" ? inr(r.interest_234c) : r.interest_if_missed > 0 ? <span className="tiny muted">{inr(r.interest_if_missed)} if not paid</span> : "–"}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
            <ol className="small" style={{ margin: 0, paddingLeft: 20 }}>{s.steps.map((x, i) => <li key={i}>{x}</li>)}</ol>
          </section>
          <PaymentsForm key={v.fy} v={v} onSaved={setV} />
        </>
      )}

      <section className="card stack" style={{ gap: 8 }}>
        <h2 className="h2">The rules, in plain words</h2>
        <ul className="small" style={{ margin: 0, paddingLeft: 20 }}>
          <li>15% of the year's tax less TDS by 15 June, 45% by 15 September, 75% by 15 December and all of it by 15 March.</li>
          <li>Capital gains and dividends that arise after a due date go into the instalments still to come (by 31 March when none is left), without interest.</li>
          <li>Section 234C: 1% a month on each instalment's shortfall, for 3 months (1 month for March). None for June when 12% was paid by then, none for September when 36% was.</li>
          <li>Section 234B: when advance tax paid by 31 March is under 90% of the tax, 1% a month on the shortfall from 1 April until it is paid.</li>
          <li>From FY 2026-27 the Income-tax Act, 2025 numbers these sections 404 (who pays), 424 (234B) and 425 (234C).</li>
        </ul>
        <ul className="small muted" style={{ margin: 0, paddingLeft: 20 }}>{v.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
        <AsOf parts={[["Worked out", v.as_of]]} />
      </section>
    </div>
  );
}

function PaymentsForm({ v, onSaved }: { v: Advance; onSaved: (a: Advance) => void }) {
  const { fail, notify } = useApp();
  const [tds, setTds] = useState(v.inputs?.tds ? String(v.inputs.tds) : "");
  const [rows, setRows] = useState<{ d: string; amount: string }[]>((v.inputs?.paid ?? []).map((p) => ({ d: p.d, amount: String(p.amount) })));
  const [saving, setSaving] = useState(false);
  const t = num(tds);
  const bad = Number.isNaN(t) || rows.some((r) => !r.d || Number.isNaN(num(r.amount)));
  const save = async () => {
    setSaving(true);
    try {
      onSaved(await api<Advance>("/money/advance-tax", { method: "PUT", body: { fy: v.fy, tds: t, paid: rows.filter((r) => num(r.amount) > 0).map((r) => ({ d: r.d, amount: num(r.amount) })) } }));
      notify("Saved. The instalments are updated.");
      track("advance tax saved", { payments: rows.length });
    } catch (e) { fail(e); } finally { setSaving(false); }
  };
  return (
    <section className="card stack" style={{ gap: 12 }} aria-label="TDS and advance tax paid">
      <h2 className="h2">TDS and advance tax paid, {v.label}</h2>
      <div className="row" style={{ gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label className="field" style={{ width: 220 }}>
          <span>TDS for the year (₹) <Info label="About TDS">All tax deducted at source for the year: on salary, interest, dividends and the like. Form 26AS or the AIS lists it.{v.dividend_tds ? ` The TDS expected on your dividends is ${inr(v.dividend_tds)}.` : ""}</Info></span>
          <input value={tds} inputMode="decimal" placeholder="e.g. 50000" onChange={(e) => setTds(e.target.value)} aria-label="TDS for the year" />
        </label>
      </div>
      <div className="stack" style={{ gap: 8 }}>
        <span className="small muted" style={{ fontWeight: 600 }}>Advance tax paid</span>
        {rows.length === 0 && <p className="small muted" style={{ margin: 0 }}>None entered.</p>}
        {rows.map((r, i) => (
          <div key={i} className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
            <label className="field" style={{ width: 180 }}><span>Date paid</span>
              <input type="date" value={r.d} onChange={(e) => setRows((x) => x.map((y, j) => (j === i ? { ...y, d: e.target.value } : y)))} aria-label={`Payment ${i + 1} date`} />
            </label>
            <label className="field" style={{ width: 180 }}><span>Amount (₹)</span>
              <input value={r.amount} inputMode="decimal" onChange={(e) => setRows((x) => x.map((y, j) => (j === i ? { ...y, amount: e.target.value } : y)))} aria-label={`Payment ${i + 1} amount`} />
            </label>
            <button className="btn quiet sm" onClick={() => setRows((x) => x.filter((_, j) => j !== i))} aria-label={`Remove payment ${i + 1}`}>Remove</button>
          </div>
        ))}
        <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
          {rows.length < 24 && <button className="btn quiet sm" onClick={() => setRows((x) => [...x, { d: "", amount: "" }])}>Add a payment</button>}
          <button className="btn sm" disabled={bad || saving} onClick={save}>{saving ? "Saving…" : "Save and update"}</button>
        </div>
        {bad && <p className="tiny neg" style={{ margin: 0 }}>Enter amounts in rupees, 0 or more, and a date for each payment.</p>}
      </div>
    </section>
  );
}

// ---------- the long-term exemption ----------
function LtcgTab() {
  const { fail } = useApp();
  const [v, setV] = useState<Ltcg | null>(null);
  const [within, setWithin] = useState(90);
  useEffect(() => { api<Ltcg>("/money/ltcg").then(setV).catch(fail); }, [fail]);
  if (!v) return <Loading label="Checking your lots" />;
  if (!v.trades) {
    return (
      <Empty title="No trades yet">
        <p className="muted" style={{ maxWidth: 520 }}>Upload your tradebooks on the <Link className="link" to="/tax-report">tax report</Link> to see the exemption used and your open lots.</p>
      </Empty>
    );
  }
  const name = (k: string) => v.names[k]?.symbol ?? k;
  const ex = v.exemption;
  const soon = v.soon.filter((r) => r.days_left <= within);
  return (
    <div className="stack" style={{ gap: 20 }}>
      <section className="card stack" style={{ gap: 14 }} aria-label="Long-term exemption">
        <h2 className="h2">Long-term exemption, {v.label}</h2>
        <div className="stat-row">
          <div className="stat"><span className="tiny muted">Used by gains realised</span><b className="num" aria-label="Exemption used">{inr(ex.used)}</b>
            <span className="tiny muted">of {inr(ex.limit)} · {inr(ex.left)} left</span>
            {ex.limit > 0 && <div className="seg-bar" aria-hidden><i style={{ width: `${Math.max(0, Math.min(100, (ex.used / ex.limit) * 100))}%` }} /></div>}
          </div>
          <div className="stat"><span className="tiny muted">Long-term gains realised (net)</span><b className={`num ${signClass(ex.realised_lt_net)}`}>{inr(ex.realised_lt_net)}</b><span className="tiny muted">short-term {inr(ex.realised_st_net)}</span></div>
          <div className="stat"><span className="tiny muted">Open long-term lots</span><b className="num">{v.open_lt.lots}</b><span className="tiny muted">unrealised gains {inr(v.open_lt.gains)}{v.open_lt.losses < 0 ? ` · losses ${inr(v.open_lt.losses)}` : ""}</span></div>
          <div className="stat"><span className="tiny muted">Turning long-term soon</span><b className="num">{v.soon_counts["90"]}</b><span className="tiny muted">{v.soon_counts["30"]} in 30 days · {v.soon_counts["60"]} in 60 · {v.soon_counts["90"]} in 90</span></div>
        </div>
        <p className="small" style={{ margin: 0 }}>{inr(ex.left)} of this year's {inr(ex.limit)} exemption is unused. It doesn't carry forward to next year.</p>
        {v.locked && <Locked text="Each open lot's long-term gain and the lots turning long-term are on the Pro plan." />}
      </section>

      {!v.locked && (
        <section className="card stack" style={{ gap: 12 }}>
          <h2 className="h2">Open long-term lots at today's price</h2>
          {v.long.length === 0 ? <p className="small muted" style={{ margin: 0 }}>No open lot has been held for more than 12 months{v.unpriced ? " with a price today" : ""}.</p> : (
            <div className="table-wrap">
              <table aria-label="Open long-term lots">
                <thead><tr><th style={{ textAlign: "left" }}>Stock</th><th>Bought</th><th>Qty</th><th>Cost for tax</th><th>Value today</th><th>Gain if sold today</th></tr></thead>
                <tbody>{v.long.map((r, i) => (
                  <tr key={i} title={r.text}>
                    <td style={{ textAlign: "left" }}><b>{name(r.key)}</b>{r.grandfathered && <span className="tiny muted"> grandfathered</span>}{r.bonus && <span className="tiny muted"> bonus</span>}</td>
                    <td className="num">{dateOnly(r.bought)}</td><td className="num">{qtyText(r.qty)}</td><td className="num">{inr(r.cost)}</td><td className="num">{inr(r.value)}</td>
                    <td className={`num ${signClass(r.gain)}`}>{inr(r.gain)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
          <p className="tiny muted" style={{ margin: 0 }}>Each figure is arithmetic: if a lot were sold today at the latest price, its long-term gain would be the value less the cost for tax (with charges, and the 31 Jan 2018 price for older lots).</p>
        </section>
      )}

      {!v.locked && (
        <section className="card stack" style={{ gap: 12 }}>
          <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
            <h2 className="h2">Turning long-term</h2>
            <div className="seg" role="radiogroup" aria-label="Within">
              {[30, 60, 90].map((n) => <button key={n} role="radio" aria-checked={within === n} aria-pressed={within === n} onClick={() => setWithin(n)}>{n} days</button>)}
            </div>
          </div>
          {soon.length === 0 ? <p className="small muted" style={{ margin: 0 }}>No open lot turns long-term in the next {within} days.</p> : (
            <div className="table-wrap">
              <table aria-label="Lots turning long-term">
                <thead><tr><th style={{ textAlign: "left" }}>Stock</th><th>Bought</th><th>Qty</th><th>Long-term from</th><th>Days left</th><th>Gain today</th></tr></thead>
                <tbody>{soon.map((r, i) => (
                  <tr key={i} title={r.text}>
                    <td style={{ textAlign: "left" }}><b>{name(r.key)}</b></td>
                    <td className="num">{dateOnly(r.bought)}</td><td className="num">{qtyText(r.qty)}</td><td className="num">{dateOnly(r.long_from)}</td>
                    <td className="num">{r.days_left}</td><td className={`num ${signClass(r.gain)}`}>{inr(r.gain)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
          <p className="tiny muted" style={{ margin: 0 }}>A sale before the date shown is short-term (20% from 23 July 2024); from that date it is long-term (12.5% above the exemption).</p>
        </section>
      )}

      {!v.locked && (
        <section className="card stack" style={{ gap: 12 }}>
          <h2 className="h2">Open lots below cost</h2>
          {v.below_cost.rows.length === 0 ? <p className="small muted" style={{ margin: 0 }}>No open lot is below its cost at today's price.</p> : (
            <div className="table-wrap">
              <table aria-label="Open lots below cost">
                <thead><tr><th style={{ textAlign: "left" }}>Stock</th><th>Bought</th><th>Qty</th><th>Below cost by</th><th>Term today</th></tr></thead>
                <tbody>{v.below_cost.rows.map((r, i) => (
                  <tr key={i}>
                    <td style={{ textAlign: "left" }}><b>{name(r.key)}</b></td><td className="num">{dateOnly(r.bought)}</td><td className="num">{qtyText(r.qty)}</td>
                    <td className="num neg">{inr(r.loss)}</td><td className="small">{r.term === "LT" ? "Long-term" : `Short-term, long-term from ${dateOnly(r.long_from)}`}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </section>
      )}

      <section className="card stack" style={{ gap: 8 }}>
        <h2 className="h2">The facts behind it</h2>
        <ul className="small" style={{ margin: 0, paddingLeft: 20 }}>{v.facts.map((f, i) => <li key={i}>{f}</li>)}</ul>
        {v.unpriced > 0 && <p className="tiny muted" style={{ margin: 0 }}>{v.unpriced} lot{v.unpriced === 1 ? " has" : "s have"} no price today{v.prices ? "" : " (live prices are offline right now)"}.</p>}
        <AsOf parts={[["Prices", v.as_of]]} />
      </section>
    </div>
  );
}
