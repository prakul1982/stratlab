import { Fragment, useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago } from "../lib/format";

type View = { currencies: Record<string, Row>; rates_at: string | null; rate_errors: string[] };

type Row = { symbol: string; name: string; basic: number; pro: number; basic_year: number; pro_year: number; charged_in: string;
  auto: boolean; rate: number | null;
  plan_basic: string | null; plan_pro: string | null; plan_basic_year: string | null; plan_pro_year: string | null };
const PRICE = ["basic", "pro", "basic_year", "pro_year"] as const;
const PLAN = ["plan_basic", "plan_pro", "plan_basic_year", "plan_pro_year"] as const;
const LABEL: Record<string, string> = { basic: "Basic / month", pro: "Pro / month", basic_year: "Basic / year", pro_year: "Pro / year" };

/** Prices outside India, per currency, and the Razorpay plan that charges each one (blank: charged in rupees). */
export function PricesPanel() {
  const { fail, notify } = useApp();
  const [rows, setRows] = useState<Record<string, Row> | null>(null);
  const [fx, setFx] = useState<{ at: string | null; errors: string[] }>({ at: null, errors: [] });
  const show = (x: View) => { setRows(x.currencies); setFx({ at: x.rates_at, errors: x.rate_errors }); };
  const [edit, setEdit] = useState<Record<string, Partial<Record<string, string>>>>({});
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<View>("/admin/prices").then(show).catch(fail); }, [fail]);
  const readRates = async () => {
    setBusy(true);
    try { show(await api<View>("/admin/prices/rates", { method: "POST" })); notify("Exchange rates read."); } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const automatic = async (c: string) => {
    setBusy(true);
    try {
      show(await api<View>("/admin/prices", { method: "PUT", body: { currencies: { [c]: { basic: null, pro: null, basic_year: null, pro_year: null } } } }));
      setEdit((e) => { const n = { ...e }; delete n[c]; return n; });
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const val = (c: string, f: string) => edit[c]?.[f] ?? String((rows?.[c] as unknown as Record<string, unknown>)?.[f] ?? "");
  const set = (c: string, f: string, v: string) => setEdit((e) => ({ ...e, [c]: { ...e[c], [f]: v } }));
  const save = async () => {
    const body: Record<string, Record<string, number | string | null>> = {};
    for (const [c, ch] of Object.entries(edit)) {
      body[c] = {};
      for (const [f, v] of Object.entries(ch)) body[c][f] = (PRICE as readonly string[]).includes(f) ? (v?.trim() ? Number(v) : null) : (v ?? "").trim();
    }
    setBusy(true);
    try {
      show(await api<View>("/admin/prices", { method: "PUT", body: { currencies: body } })); setEdit({}); notify("Prices saved.");
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  return (
    <section className="card stack" style={{ gap: 12 }}>
      <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
        <h2 className="h2">Prices outside India</h2>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn quiet sm" disabled={busy} onClick={readRates}>Read today's rates</button>
          <button className="btn sm" disabled={busy || !Object.keys(edit).length} onClick={save}>{busy ? "Saving…" : "Save changes"}</button>
        </div>
      </div>
      <p className="small muted" style={{ maxWidth: "80ch", margin: 0 }}>Visitors see prices in their own currency (picked from their country; they can switch).
        <b> Automatic</b> prices follow the rupee price at today's exchange rate, rounded to a tidy amount, so changing the rupee price changes them all. Type a price to fix it instead.
        No Razorpay plan is needed: without one, visitors pay the rupee price and their card converts it. Only to charge in a currency itself, create a plan in Razorpay in
        that currency for the same amount, fix the price here to match, and paste the plan ID.</p>
      <p className="tiny muted" style={{ margin: 0 }}>{fx.at ? `Exchange rates read ${ago(fx.at)}.` : "Exchange rates not read yet: the built-in amounts are shown."}
        {fx.errors.length ? ` Couldn't read: ${fx.errors.map((e) => e.split(":")[0]).join(", ")} (last rate kept).` : ""}</p>
      {!rows ? <p className="small muted">Loading…</p> : (
        <div className="table-wrap"><table>
          <thead><tr><th>Currency</th>{PRICE.map((f) => <th key={f} className="num">{LABEL[f]}</th>)}<th>Price</th><th>Charged in</th><th /></tr></thead>
          <tbody>{Object.entries(rows).filter(([c]) => c !== "INR").map(([c, r]) => (
            <Fragment key={c}>
              <tr>
                <td><b>{c}</b> <span className="tiny muted">{r.name}{r.rate ? ` · ₹${r.rate.toLocaleString("en-IN", { maximumFractionDigits: r.rate < 1 ? 4 : 2 })}` : ""}</span></td>
                {PRICE.map((f) => <td key={f} className="num"><input value={val(c, f)} onChange={(e) => set(c, f, e.target.value)} inputMode="decimal"
                  aria-label={`${c} ${LABEL[f]}`} style={{ width: 90, textAlign: "right" }} /></td>)}
                <td>{r.auto ? <span className="badge next">Automatic</span>
                  : <button className="btn quiet sm" disabled={busy} onClick={() => automatic(c)} title="Follow the rupee price again">Fixed · make automatic</button>}</td>
                <td><span className={`badge ${r.charged_in === c ? "pass" : "skip"}`}>{r.charged_in === c ? c : "Rupees"}</span></td>
                <td><button className="btn quiet sm" onClick={() => setOpen(open === c ? null : c)}>{open === c ? "Hide plans" : "Razorpay plans"}</button></td>
              </tr>
              {open === c && (
                <tr><td colSpan={8}>
                  <div className="row wrap" style={{ gap: 10 }}>{PLAN.map((f) => (
                    <label key={f} className="stack tiny" style={{ gap: 2 }}>{LABEL[f.replace("plan_", "")]} plan ID
                      <input value={val(c, f)} onChange={(e) => set(c, f, e.target.value)} placeholder="plan_…" style={{ width: 190 }} /></label>))}
                  </div>
                </td></tr>
              )}
            </Fragment>
          ))}</tbody>
        </table></div>
      )}
    </section>
  );
}
