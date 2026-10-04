import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, dataUrl } from "../../lib/api";
import { useApp } from "../../lib/app";
import { ago, dateOnly, money, pct, price, qty as qtyText, signClass } from "../../lib/format";
import { AsOf, Empty, Info, Loading } from "../../components/ui";
import { Trash, Upload } from "../../components/Icons";
import { track } from "../../lib/analytics";

type Kind = "equity" | "debt" | "hybrid" | "other";
type Scheme = {
  key: string; name: string; amc: string; folio: string; isin: string; amfi: string; category: string; broad: string; sub: string;
  kind: Kind; kind_auto: Kind; kind_set: boolean; units: number; nav: number | null; nav_date: string | null; nav_source: "daily" | "statement" | null;
  invested: number | null; value: number | null; gain: number | null; gain_pct: number | null; xirr: number | null; realised: number | null;
  cost_unknown: boolean; short_units: number | null; elss: { locked_units: number; next_free: string; all_free: string } | null; txns: number;
  fmv_2018: number | null; fmv_yours: boolean;
};
type Bucket = { key: string; label: string; rate: number; gains: number; after_setoff: number; exempt: number; taxable: number; tax: number; slab?: boolean };
type Sale = { key: string; bought: string; sold: string; qty: number; cost: number; sale: number; gain: number; term: "ST" | "LT"; gf: "applied" | "missing" | null; rate: number | null; kind?: Kind };
type Side = { gains: number; losses: number; net: number; sales: number };
type Year = {
  fy: number; label: string; stcg: Side; ltcg: Side; exemption: { limit: number; used: number; left: number }; buckets: Bucket[]; steps: string[];
  tax: number; tax_with_cess: number; carry_forward: { st: number; lt: number }; count: number; rows: Sale[]; dividends: number; stt: number;
  exempt_old: number | null;
};
type Gains = { years: Year[]; current_fy: number; notes: string[]; gf_missing: string[]; unknown_units: Record<string, number>; flags: string[] };
type View = {
  schemes: Scheme[]; allocation: { broad: string; value: number; pct: number | null; schemes: number; subs: { sub: string; value: number; pct: number | null }[] }[];
  total: { value: number; invested: number; gain: number; xirr: number | null; held: number; schemes: number; unknown_cost: number; nav_dates: [string, string] | null };
  gains: Gains | null; gains_allowed: boolean; gains_plan: string; limit: number | null; files: { name: string; kind: string; txns: number; at: string }[];
  updated_at: string | null; txns: number; kinds: Record<Kind, string>; nav_read_at: string | null; assumptions: string[]; disclaimer: string; as_of: string;
};
type Problem = { line?: number; text: string; reason: string };
type ImportReply = { kind: "cas" | "csv"; added: number; duplicates: number; over_limit: string[]; schemes: number; problems: Problem[]; limit: number | null; upgrade: string | null; view: View };

const MAX_MB = 5;
const inr = (v: number | null | undefined) => money(v, "INR", 0);
const rate = (r: number | null, slab?: boolean) => (r == null || slab ? "Slab" : `${+(r * 100).toFixed(2)}%`);
const xirrText = (x: number | null) => (x == null ? "–" : pct(x * 100));
const KIND_SHORT: Record<Kind, string> = { equity: "Equity-oriented", debt: "Debt", hybrid: "Other (35–65% equity)", other: "Other (under 35% equity)" };

export function MutualFundsPage() {
  const { fail, notify } = useApp();
  const [view, setView] = useState<View | null>(null);
  const [picked, setPicked] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"add" | "replace">("add");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportReply | null>(null);
  const [fy, setFy] = useState<number | null>(null);
  const [allSales, setAllSales] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  const show = useCallback((v: View) => {
    setView(v);
    setFy((cur) => (cur != null && v.gains?.years.some((y) => y.fy === cur) ? cur : v.gains?.years[0]?.fy ?? null));
  }, []);
  useEffect(() => { api<View>("/money/mutual-funds").then(show).catch(fail); }, [show, fail]);

  const isPdf = !!picked && (/\.pdf$/i.test(picked.name) || picked.type === "application/pdf");
  const send = async () => {
    if (!picked) { notify("Pick your CAS PDF or a CSV first."); return; }
    if (picked.size > MAX_MB * 1024 * 1024) { notify(`That file is larger than ${MAX_MB} MB. A CAS is usually much smaller.`); return; }
    setBusy(true);
    try {
      const data = await dataUrl(picked);
      const r = await api<ImportReply>("/money/mutual-funds/import", { method: "POST", body: { filename: picked.name, data, password: isPdf ? password : "", mode } });
      track("mutual funds imported", { kind: r.kind, added: r.added });
      setResult(r);
      show(r.view);
      setPicked(null);
      if (file.current) file.current.value = "";
    } catch (e) { fail(e); } finally {
      setPassword("");          // used once to open the file, then forgotten
      setBusy(false);
    }
  };

  const setKind = async (key: string, kind: Kind | null) => {
    try { show(await api<View>("/money/mutual-funds/kind", { method: "PUT", body: { key, kind } })); notify("Saved. The gains are worked out again."); }
    catch (e) { fail(e); }
  };
  const setFmv = async (key: string, nav: number | null) => {
    try { show(await api<View>("/money/mutual-funds/fmv", { method: "PUT", body: { key, nav } })); notify(nav ? "Saved. Units held on 31 Jan 2018 now use it." : "Cleared."); }
    catch (e) { fail(e); }
  };
  const remove = () => {
    if (!confirm("Delete my mutual fund data? Every scheme and transaction is removed from StratLab. Your folios aren't touched.")) return;
    api("/money/mutual-funds", { method: "DELETE" }).then(() => { setResult(null); return api<View>("/money/mutual-funds").then(show); })
      .then(() => notify("Your mutual fund data is deleted.")).catch(fail);
  };

  const schemes = view?.schemes ?? [];
  const held = schemes.filter((s) => s.units > 0);
  const name = useCallback((k: string) => schemes.find((s) => s.key === k)?.name ?? k, [schemes]);
  const y = useMemo(() => view?.gains?.years.find((x) => x.fy === fy) ?? null, [view, fy]);
  const t = view?.total;
  const navWhen = t?.nav_dates ? (t.nav_dates[0] === t.nav_dates[1] ? dateOnly(t.nav_dates[0]) : `${dateOnly(t.nav_dates[0])} to ${dateOnly(t.nav_dates[1])}`) : null;

  return (
    <div className="stack" style={{ gap: 24 }}>
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Money · Mutual funds</span>
        <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.1 }}>Your mutual funds, in one place</h1>
        <p className="page-sub">Upload your Consolidated Account Statement to see every scheme's value at the latest NAV, what you put in, the gain, XIRR, your mix by category, and capital gains for each financial year. Facts and arithmetic only, never advice. Only you can see your funds, and you can delete them at any time.</p>
      </div>
      <div className="banner" role="note"><span>{view?.disclaimer ?? "Facts and arithmetic from your own statement, valued at the latest published NAV. Not investment or tax advice."}</span></div>

      <section className="card stack" style={{ gap: 14 }}>
        <div className="stack" style={{ gap: 4 }}>
          <h2 className="h2">Upload your statement</h2>
          <p className="small muted" style={{ margin: 0 }}>Ask CAMS or KFintech for the <b>detailed</b> Consolidated Account Statement (with transactions), from the date of your first investment, and upload the PDF as it was emailed to you, with its password. The PDF is opened in memory to read your transactions; neither the file nor the password is kept. Or upload a CSV with the columns Date, Scheme, ISIN or AMFI code, Units, Amount and Type (purchase, SIP, redemption, switch in or out, dividend, stamp duty or STT).</p>
        </div>
        <div className="mf-upload">
          <label className={`btn quiet${busy ? " disabled" : ""}`} style={{ cursor: busy ? "wait" : "pointer" }}>
            <Upload size={18} />{picked ? "Pick another file" : "Pick CAS PDF or CSV"}
            <input ref={file} type="file" accept=".pdf,.csv,application/pdf,text/csv" hidden disabled={busy}
              onChange={(e) => setPicked(e.target.files?.[0] ?? null)} aria-label="CAS PDF or CSV file" />
          </label>
          {picked && <span className="small" style={{ overflowWrap: "anywhere" }}>{picked.name}</span>}
          {isPdf && (
            <label className="field">PDF password
              <input type="password" value={password} autoComplete="off" spellCheck={false} placeholder="As set when you asked for it, often your PAN"
                onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") send(); }} aria-label="PDF password" />
            </label>
          )}
          <button className="btn" disabled={busy || !picked} onClick={send}>{busy ? "Reading…" : "Read my funds"}</button>
        </div>
        {schemes.length > 0 && (
          <div className="seg" role="radiogroup" aria-label="What the file does" style={{ alignSelf: "flex-start" }}>
            <button role="radio" aria-checked={mode === "add"} aria-pressed={mode === "add"} onClick={() => setMode("add")}>Add to my funds</button>
            <button role="radio" aria-checked={mode === "replace"} aria-pressed={mode === "replace"} onClick={() => setMode("replace")}>Start again with this file</button>
          </div>
        )}
        {result && (
          <div className="stack" style={{ gap: 8 }} role="status">
            <p className="small" style={{ margin: 0 }}>
              <b>{result.kind === "cas" ? "Read your statement" : "Read as a CSV file"}:</b> {result.added} transaction{result.added === 1 ? "" : "s"} added
              {result.duplicates > 0 && `, ${result.duplicates} already saved (skipped)`}, from {result.schemes} scheme{result.schemes === 1 ? "" : "s"}.
            </p>
            {result.over_limit.length > 0 && (
              <p className="small" style={{ margin: 0 }}>Your plan keeps {result.limit} schemes, so {result.over_limit.length} {result.over_limit.length === 1 ? "was" : "were"} left out: {result.over_limit.slice(0, 8).join(", ")}{result.over_limit.length > 8 ? "…" : ""}. {result.upgrade} <Link className="link" to="/plans">See plans</Link></p>
            )}
            {result.problems.length > 0 && (
              <ul className="tiny muted" style={{ margin: 0, paddingLeft: 18 }} aria-label="Lines left out">
                {result.problems.slice(0, 20).map((p, i) => <li key={i}>{p.line ? `Line ${p.line}: ` : ""}{p.text ? `${p.text} · ` : ""}{p.reason}</li>)}
              </ul>
            )}
          </div>
        )}
        {view && view.files.length > 0 && (
          <p className="tiny muted" style={{ margin: 0 }}>{view.txns.toLocaleString()} transactions from {view.files.length} file{view.files.length === 1 ? "" : "s"}{view.updated_at ? ` · updated ${ago(view.updated_at)}` : ""}</p>
        )}
      </section>

      {!view && <Loading label="Opening your mutual funds" />}
      {view && schemes.length === 0 && (
        <Empty title="No funds yet">
          <p className="muted">Upload your CAS above to see your schemes, their value and your gains.</p>
        </Empty>
      )}

      {view && t && schemes.length > 0 && (
        <>
          <div className="stat-row">
            <div className="stat"><span className="tiny muted">Current value</span><b className="num">{inr(t.value)}</b><span className="tiny muted">{t.held} scheme{t.held === 1 ? "" : "s"} held</span></div>
            <div className="stat"><span className="tiny muted">Invested <Info label="What invested means">The cost of the units you still hold, matched first in, first out, including stamp duty. Units sold or switched out are not in it.</Info></span><b className="num">{inr(t.invested)}</b>{t.unknown_cost > 0 && <span className="tiny muted">{t.unknown_cost} scheme{t.unknown_cost === 1 ? "" : "s"} without a known cost left out</span>}</div>
            <div className="stat"><span className="tiny muted">Unrealised gain</span><b className={`num ${signClass(t.gain)}`}>{inr(t.gain)}</b></div>
            <div className="stat"><span className="tiny muted">XIRR, all schemes <Info label="What XIRR is">The yearly rate of return that accounts for when each rupee went in and came out: every purchase, redemption and dividend paid out, with today's value as the last amount.</Info></span><b className={`num ${signClass(t.xirr)}`}>{xirrText(t.xirr)}</b></div>
          </div>
          <p className="tiny muted" style={{ margin: "-12px 0 0" }}>{navWhen ? `Valued at the NAV of ${navWhen}.` : "No NAV is available yet."}</p>
          <AsOf parts={[["NAVs read", view.nav_read_at]]} />

          <section className="card stack" style={{ gap: 12 }}>
            <h2 className="h2">By category</h2>
            <div className="stack" style={{ gap: 10 }}>
              {view.allocation.map((a) => (
                <div key={a.broad} className="seg-row">
                  <div className="spread small" style={{ gap: 10 }}><span>{a.broad} <span className="muted tiny">· {a.schemes} scheme{a.schemes === 1 ? "" : "s"}{a.subs.length > 0 ? ` · ${a.subs.map((s) => s.sub).join(", ")}` : ""}</span></span><span className="num">{a.pct == null ? "–" : `${a.pct.toFixed(1)}%`}</span></div>
                  <div className="seg-bar"><i style={{ width: `${Math.max(1, Math.min(100, a.pct ?? 0))}%` }} /></div>
                </div>
              ))}
            </div>
            <p className="tiny muted" style={{ margin: 0 }}>Share of the current value, by each scheme's official category.</p>
          </section>

          <section className="card stack" style={{ gap: 12 }}>
            <h2 className="h2">Schemes</h2>
            <div className="table-wrap">
              <table aria-label="Schemes">
                <thead><tr><th style={{ textAlign: "left" }}>Scheme</th><th>Units</th><th>NAV</th><th>Invested</th><th>Value</th><th>Gain</th><th>XIRR</th><th style={{ textAlign: "left" }}>Taxed as</th></tr></thead>
                <tbody>{schemes.map((s) => (
                  <tr key={s.key}>
                    <td style={{ textAlign: "left", minWidth: 220, whiteSpace: "normal" }}>
                      <b>{s.name}</b>
                      <div className="tiny muted">Folio {s.folio}{s.category ? ` · ${s.category}` : ""}</div>
                      {s.elss && <div className="tiny">ELSS lock-in: {qtyText(s.elss.locked_units)} units locked; the next free on {dateOnly(s.elss.next_free)}, all by {dateOnly(s.elss.all_free)}.</div>}
                      {s.cost_unknown && <div className="tiny neg">Some units have no purchase in the statement, so their cost isn't known. A statement from your first investment fixes this.</div>}
                    </td>
                    <td className="num">{qtyText(s.units)}</td>
                    <td className="num">{price(s.nav, "INR")}<div className="tiny muted">{s.nav_date ? dateOnly(s.nav_date) : "–"}{s.nav_source === "statement" ? " · statement" : ""}</div></td>
                    <td className="num">{inr(s.invested)}</td>
                    <td className="num">{inr(s.value)}</td>
                    <td className={`num ${signClass(s.gain)}`}>{s.gain == null ? "–" : <>{inr(s.gain)} <span className="tiny">{pct(s.gain_pct)}</span></>}</td>
                    <td className={`num ${signClass(s.xirr)}`}>{xirrText(s.xirr)}</td>
                    <td style={{ textAlign: "left" }}>
                      <select className="input" value={s.kind} aria-label={`How ${s.name} is taxed`} onChange={(e) => setKind(s.key, e.target.value === s.kind_auto ? null : e.target.value as Kind)}>
                        {(Object.keys(KIND_SHORT) as Kind[]).map((k) => <option key={k} value={k}>{KIND_SHORT[k]}</option>)}
                      </select>
                      <div className="tiny muted">{s.kind_set ? "Set by you" : "From the category"}</div>
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <p className="tiny muted" style={{ margin: 0 }}>Gain is the current value less the cost of the units held. XIRR counts every purchase, redemption and dividend paid out in the scheme; it isn't shown for less than 30 days, or when the cost of some units isn't known. "Taxed as" is read from the category; change it where your fund's documents say otherwise.</p>
            <details className="small">
              <summary className="tiny" style={{ minHeight: 32, display: "flex", alignItems: "center", cursor: "pointer" }}>What each tax kind means</summary>
              <ul className="tiny muted" style={{ margin: "6px 0 0", paddingLeft: 18 }}>{(Object.keys(view.kinds) as Kind[]).map((k) => <li key={k}>{view.kinds[k]}</li>)}</ul>
            </details>
          </section>

          {!view.gains_allowed && (
            <div className="banner"><span>Capital gains for each financial year, and every scheme you hold, are on the {view.gains_plan} plan.</span><Link to="/plans" className="btn sm">See plans</Link></div>
          )}
          {view.gains && (
            <section className="card stack" style={{ gap: 12 }} aria-label="Capital gains">
              <div className="spread" style={{ flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
                <h2 className="h2">Capital gains by financial year</h2>
                {view.gains.years.length > 0 && (
                  <label className="field" style={{ minWidth: 200 }}>Financial year
                    <select value={fy ?? ""} onChange={(e) => { setFy(Number(e.target.value)); setAllSales(false); }} aria-label="Financial year">
                      {view.gains.years.map((x) => <option key={x.fy} value={x.fy}>{x.label}{x.fy === view.gains!.current_fy ? " (this year)" : ""}</option>)}
                    </select>
                  </label>
                )}
              </div>
              {view.gains.years.length === 0 && <p className="small muted" style={{ margin: 0 }}>No redemptions or switches out yet, so no gains have been realised.</p>}
              {y && (
                <>
                  <div className="stat-row">
                    <div className="stat"><span className="tiny muted">Short-term (net)</span><b className={`num ${signClass(y.stcg.net)}`}>{inr(y.stcg.net)}</b></div>
                    <div className="stat"><span className="tiny muted">Long-term (net)</span><b className={`num ${signClass(y.ltcg.net)}`}>{inr(y.ltcg.net)}</b></div>
                    <div className="stat"><span className="tiny muted">Tax at special rates</span><b className="num">{inr(y.tax)}</b><span className="tiny muted">before cess; slab-rate gains are taxed with your income</span></div>
                    <div className="stat"><span className="tiny muted">Dividends paid out</span><b className="num">{inr(y.dividends)}</b><span className="tiny muted">income at your slab rate</span></div>
                  </div>
                  {y.buckets.length > 0 && (
                    <div className="table-wrap">
                      <table aria-label="Gains by rate">
                        <thead><tr><th style={{ textAlign: "left" }}>Kind</th><th>Rate</th><th>Gains</th><th>After set-off</th><th>Exempt</th><th>Taxable</th><th>Tax</th></tr></thead>
                        <tbody>{y.buckets.map((b) => (
                          <tr key={b.key}><td style={{ textAlign: "left" }}>{b.label}</td><td className="num">{rate(b.rate, b.slab)}</td><td className="num">{inr(b.gains)}</td><td className="num">{inr(b.after_setoff)}</td>
                            <td className="num">{inr(b.exempt)}</td><td className="num">{inr(b.taxable)}</td><td className="num">{b.slab ? "At your slab rate" : inr(b.tax)}</td></tr>
                        ))}</tbody>
                      </table>
                    </div>
                  )}
                  {y.steps.length > 0 && <ul className="small" style={{ margin: 0, paddingLeft: 20 }}>{y.steps.map((s, i) => <li key={i}>{s}</li>)}</ul>}
                  <p className="tiny muted" style={{ margin: 0 }}>The long-term exemption here counts your funds alone. The <Link className="link" to="/tax-report">tax report</Link> adds these gains to your shares', shares the exemption and set-off between them, and includes them in the year's total tax estimate.</p>
                  {y.count > 0 && (
                    <div className="table-wrap">
                      <table aria-label="Redemptions matched to purchases">
                        <thead><tr><th style={{ textAlign: "left" }}>Scheme</th><th>Bought</th><th>Sold</th><th>Units</th><th>Cost</th><th>Sale</th><th>Gain or loss</th><th>Term</th><th>Rate</th></tr></thead>
                        <tbody>{(allSales ? y.rows : y.rows.slice(0, 30)).map((r, i) => (
                          <tr key={i}>
                            <td style={{ textAlign: "left", minWidth: 200, whiteSpace: "normal" }}>{name(r.key)}{r.gf === "applied" && <span className="tiny muted"> grandfathered</span>}{r.gf === "missing" && <span className="tiny neg"> 31 Jan 2018 NAV missing</span>}</td>
                            <td className="num">{dateOnly(r.bought)}</td><td className="num">{dateOnly(r.sold)}</td><td className="num">{qtyText(r.qty)}</td>
                            <td className="num">{inr(r.cost)}</td><td className="num">{inr(r.sale)}</td><td className={`num ${signClass(r.gain)}`}>{inr(r.gain)}</td>
                            <td>{r.term === "LT" ? "Long" : "Short"}</td><td className="num">{rate(r.rate)}</td>
                          </tr>
                        ))}</tbody>
                      </table>
                    </div>
                  )}
                  {y.rows.length > 30 && !allSales && <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={() => setAllSales(true)}>Show all {y.rows.length}</button>}
                </>
              )}
              {view.gains.gf_missing.length > 0 && (
                <div className="stack" style={{ gap: 8 }}>
                  <p className="small" style={{ margin: 0 }}>Units held on 31 Jan 2018 cost at least that day's NAV. It isn't known for these schemes; enter it to use it:</p>
                  {view.gains.gf_missing.map((k) => <FmvRow key={k} label={name(k)} onSave={(v) => setFmv(k, v)} />)}
                </div>
              )}
              {schemes.filter((s) => s.fmv_yours).map((s) => (
                <p key={s.key} className="tiny muted" style={{ margin: 0 }}>{s.name}: your 31 Jan 2018 NAV of {price(s.fmv_2018, "INR")} is used. <button className="btn quiet sm" onClick={() => setFmv(s.key, null)}>Clear it</button></p>
              ))}
              <details className="small">
                <summary className="tiny" style={{ minHeight: 32, display: "flex", alignItems: "center", cursor: "pointer" }}>How gains are worked out</summary>
                <ul className="tiny muted" style={{ margin: "6px 0 0", paddingLeft: 18 }}>{view.gains.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
              </details>
            </section>
          )}

          <section className="stack" style={{ gap: 8 }}>
            <ul className="tiny muted" style={{ margin: 0, paddingLeft: 18, maxWidth: "80ch" }} aria-label="Assumptions">{view.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
            <p className="small muted" style={{ margin: 0, maxWidth: "80ch" }}>Your transactions are stored with your account only, used for this page, the tax report and your net worth, and never shared. As of {dateOnly(view.as_of)}.</p>
            <button className="btn danger" style={{ alignSelf: "flex-start" }} onClick={remove}><Trash size={16} />Delete my mutual fund data</button>
          </section>
        </>
      )}
      {view && held.length === 0 && schemes.length > 0 && <p className="small muted" style={{ margin: 0 }}>Every scheme in your files has been fully redeemed.</p>}
    </div>
  );
}

function FmvRow({ label, onSave }: { label: string; onSave: (v: number | null) => void }) {
  const [v, setV] = useState("");
  return (
    <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
      <label className="field" style={{ minWidth: 220, flex: "1 1 220px" }}>{label}: NAV on 31 Jan 2018 (₹)
        <input value={v} inputMode="decimal" placeholder="e.g. 42.15" onChange={(e) => setV(e.target.value)} />
      </label>
      <button className="btn sm" disabled={!(Number(v) > 0)} onClick={() => onSave(Number(v))}>Save</button>
    </div>
  );
}
