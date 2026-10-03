import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { openInvoice } from "./InvoicesCard";

type Seller = { legal_name: string; address: string; state: string; gstin: string; pan: string; lut_arn: string; email: string; prefix: string };
type Row = { number: string; date: string; total: number; currency: string; supply: string; email: string; tax: number };

/** Admin → Invoices: who the invoices are from (GST details) and every invoice of a financial year. */
export function InvoiceAdminPanel() {
  const { fail, notify } = useApp();
  const [s, setS] = useState<Seller | null>(null);
  const [states, setStates] = useState<Record<string, string>>({});
  const [rows, setRows] = useState<Row[]>([]);
  const [year, setYear] = useState("");
  const load = (y = "") => api<{ seller: Seller; states: Record<string, string>; year: string; invoices: Row[] }>(`/admin/invoices${y ? `?year=${y}` : ""}`)
    .then((x) => { setS(x.seller); setStates(x.states); setYear(x.year); setRows(x.invoices); }).catch(fail);
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const save = async () => {
    try { const x = await api<{ seller: Seller }>("/admin/invoices/seller", { method: "PUT", body: s }); setS(x.seller); notify("Invoice details saved."); }
    catch (e) { fail(e); }
  };
  const csv = () => {
    const lines = [["number", "date", "email", "supply", "currency", "total", "tax"].join(",")];
    for (const r of rows) lines.push([r.number, r.date, r.email, r.supply, r.currency, r.total, r.tax].map((x) => `"${String(x ?? "").replace(/"/g, '""')}"`).join(","));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" })); a.download = `stratlab-invoices-${year}.csv`; a.click();
  };
  const f = (k: keyof Seller, label: string, hint?: string) => s && (
    <label className="field">{label}<input value={s[k]} onChange={(e) => setS({ ...s, [k]: e.target.value })} />{hint && <span className="hint">{hint}</span>}</label>);
  return (
    <section className="card stack" style={{ gap: 12 }}>
      <h2 className="h2">Invoices</h2>
      <p className="small muted" style={{ margin: 0, maxWidth: "80ch" }}>Every payment gets an invoice, numbered per financial year. Prices include GST: 18% split CGST + SGST within your state,
        IGST across states. Customers outside India are an export of services: zero-rated with your LUT number, otherwise IGST is shown as included. Without a GSTIN the
        invoice says you aren't registered for GST. Have your accountant confirm the setup.</p>
      {s && (
        <div className="stack" style={{ gap: 10, maxWidth: 560 }}>
          {f("legal_name", "Legal name")}{f("address", "Address")}
          <label className="field">State<select value={s.state} onChange={(e) => setS({ ...s, state: e.target.value })}>
            <option value="">Choose…</option>{Object.entries(states).map(([c, n]) => <option key={c} value={c}>{n}</option>)}</select></label>
          {f("gstin", "GSTIN", "Leave empty if not registered for GST.")}{f("pan", "PAN")}
          {f("lut_arn", "LUT ARN", "From the Letter of Undertaking filed on the GST portal each year, to export without paying IGST.")}
          {f("email", "Billing email")}{f("prefix", "Invoice number prefix", "e.g. SL gives SL/2026-27/0001")}
          <button className="btn sm" style={{ alignSelf: "flex-start" }} onClick={save}>Save details</button>
        </div>
      )}
      <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
        <b className="small">Financial year {year}: {rows.length} invoice{rows.length === 1 ? "" : "s"}</b>
        <span className="row" style={{ gap: 8 }}>
          <input className="input" placeholder="2026-27" style={{ width: 100 }} onKeyDown={(e) => { if (e.key === "Enter") load((e.target as HTMLInputElement).value.trim()); }} aria-label="Financial year" />
          {!!rows.length && <button className="btn quiet sm" onClick={csv}>Download CSV</button>}
        </span>
      </div>
      {rows.length > 0 && <div className="table-wrap"><table>
        <thead><tr><th>Number</th><th>Date</th><th>Customer</th><th>Supply</th><th className="num">Total</th><th className="num">GST</th><th /></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.number}><td className="mono">{r.number}</td><td>{r.date}</td><td>{r.email}</td><td>{r.supply}</td>
          <td className="num">{r.currency} {r.total.toFixed(2)}</td><td className="num">{r.tax.toFixed(2)}</td>
          <td><button className="btn quiet sm" onClick={() => openInvoice(r.number).catch(fail)}>Open</button></td></tr>)}</tbody>
      </table></div>}
    </section>
  );
}
