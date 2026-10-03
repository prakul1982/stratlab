import { Fragment, useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";

type Row = { symbol: string; name: string; basic: number; pro: number; basic_year: number; pro_year: number; charged_in: string;
  plan_basic: string | null; plan_pro: string | null; plan_basic_year: string | null; plan_pro_year: string | null };
const PRICE = ["basic", "pro", "basic_year", "pro_year"] as const;
const PLAN = ["plan_basic", "plan_pro", "plan_basic_year", "plan_pro_year"] as const;
const LABEL: Record<string, string> = { basic: "Basic / month", pro: "Pro / month", basic_year: "Basic / year", pro_year: "Pro / year" };

/** Prices outside India, per currency, and the Razorpay plan that charges each one (blank: charged in rupees). */
export function PricesPanel() {
  const { fail, notify } = useApp();
  const [rows, setRows] = useState<Record<string, Row> | null>(null);
  const [edit, setEdit] = useState<Record<string, Partial<Record<string, string>>>>({});
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<{ currencies: Record<string, Row> }>("/admin/prices").then((x) => setRows(x.currencies)).catch(fail); }, [fail]);

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
      const x = await api<{ currencies: Record<string, Row> }>("/admin/prices", { method: "PUT", body: { currencies: body } });
      setRows(x.currencies); setEdit({}); notify("Prices saved.");
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  return (
    <section className="card stack" style={{ gap: 12 }}>
      <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
        <h2 className="h2">Prices outside India</h2>
        <button className="btn sm" disabled={busy || !Object.keys(edit).length} onClick={save}>{busy ? "Saving…" : "Save changes"}</button>
      </div>
      <p className="small muted" style={{ maxWidth: "80ch", margin: 0 }}>Visitors see prices in their own currency (picked from their country; they can switch). Rupee prices come from the plans themselves.
        A currency is charged in that currency once its Razorpay plans are set here: create each plan in the Razorpay dashboard in that currency with the same amount,
        then paste its plan ID. Until then visitors pay the rupee price and their card converts it.</p>
      {!rows ? <p className="small muted">Loading…</p> : (
        <div className="table-wrap"><table>
          <thead><tr><th>Currency</th>{PRICE.map((f) => <th key={f} className="num">{LABEL[f]}</th>)}<th>Charged in</th><th /></tr></thead>
          <tbody>{Object.entries(rows).filter(([c]) => c !== "INR").map(([c, r]) => (
            <Fragment key={c}>
              <tr>
                <td><b>{c}</b> <span className="tiny muted">{r.name}</span></td>
                {PRICE.map((f) => <td key={f} className="num"><input value={val(c, f)} onChange={(e) => set(c, f, e.target.value)} inputMode="decimal"
                  aria-label={`${c} ${LABEL[f]}`} style={{ width: 90, textAlign: "right" }} /></td>)}
                <td><span className={`badge ${r.charged_in === c ? "pass" : "skip"}`}>{r.charged_in === c ? c : "Rupees"}</span></td>
                <td><button className="btn quiet sm" onClick={() => setOpen(open === c ? null : c)}>{open === c ? "Hide plans" : "Razorpay plans"}</button></td>
              </tr>
              {open === c && (
                <tr><td colSpan={7}>
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
