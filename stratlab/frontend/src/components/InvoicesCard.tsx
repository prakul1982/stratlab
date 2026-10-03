import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";

type Inv = { number: string; date: string; total: number; currency: string; supply: string };
type Billing = { name?: string; address?: string; state?: string; gstin?: string; country?: string };
const SYM: Record<string, string> = { INR: "₹", USD: "$", EUR: "€", GBP: "£" };

/** Open an invoice's printable page in a new tab (signed in, so fetched rather than linked). */
export async function openInvoice(number: string) {
  const [, year, n] = number.split("/");
  const r = await api<Response>(`/billing/invoices/${year}/${n}`, { raw: true });
  const url = URL.createObjectURL(new Blob([await r.text()], { type: "text/html" }));
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** Account → Invoices: every payment's invoice, and the details printed on future ones. */
export function InvoicesCard() {
  const { fail, notify } = useApp();
  const [rows, setRows] = useState<Inv[] | null>(null);
  const [b, setB] = useState<Billing>({});
  const [states, setStates] = useState<Record<string, string>>({});
  useEffect(() => {
    api<{ invoices: Inv[]; billing: Billing; states: Record<string, string> }>("/billing/invoices")
      .then((x) => { setRows(x.invoices); setB({ country: "IN", ...x.billing }); setStates(x.states); }).catch(fail);
  }, [fail]);
  const save = async () => {
    try { const x = await api<{ billing: Billing }>("/billing/details", { method: "PUT", body: b }); setB(x.billing); notify("Billing details saved."); }
    catch (e) { fail(e); }
  };
  const india = (b.country || "IN") === "IN";
  return (
    <section className="card stack" style={{ gap: 12 }}>
      <h2 className="h2">Invoices</h2>
      {!rows ? <p className="small muted">Loading…</p> : rows.length === 0 ? <p className="small muted">No payments yet. An invoice appears here for every payment.</p> : (
        <div className="stack" style={{ gap: 0 }}>{rows.map((r) => (
          <div key={r.number} className="spread" style={{ padding: "8px 0", borderBottom: "1px solid var(--line)" }}>
            <span className="stack" style={{ gap: 0 }}><b className="mono" style={{ fontSize: 14 }}>{r.number}</b><span className="small muted">{r.date} · {r.supply}</span></span>
            <span className="row" style={{ gap: 10 }}><b>{SYM[r.currency] ?? r.currency + " "}{r.total.toLocaleString(r.currency === "INR" ? "en-IN" : "en-US", { minimumFractionDigits: 2 })}</b>
              <button className="btn quiet sm" onClick={() => openInvoice(r.number).catch(fail)}>Open</button></span>
          </div>))}</div>
      )}
      <details>
        <summary className="small" style={{ cursor: "pointer" }}>Details on your invoices{b.gstin ? ` (GSTIN ${b.gstin})` : ""}</summary>
        <div className="stack" style={{ gap: 10, marginTop: 10, maxWidth: 520 }}>
          <label className="field">Name or business name<input value={b.name ?? ""} maxLength={200} onChange={(e) => setB({ ...b, name: e.target.value })} /></label>
          <label className="field">Address<input value={b.address ?? ""} maxLength={300} onChange={(e) => setB({ ...b, address: e.target.value })} /></label>
          <label className="field">Country
            <select value={b.country || "IN"} onChange={(e) => setB({ ...b, country: e.target.value })}>
              <option value="IN">India</option><option value="US">United States</option><option value="GB">United Kingdom</option>
              <option value="AE">United Arab Emirates</option><option value="SG">Singapore</option><option value="XX">Another country</option>
            </select></label>
          {india && <label className="field">State
            <select value={b.state ?? ""} onChange={(e) => setB({ ...b, state: e.target.value })}>
              <option value="">Choose…</option>{Object.entries(states).map(([c, n]) => <option key={c} value={c}>{n}</option>)}
            </select></label>}
          {india && <label className="field">GSTIN (businesses, to claim input tax credit)<input value={b.gstin ?? ""} maxLength={15} onChange={(e) => setB({ ...b, gstin: e.target.value.toUpperCase() })} /></label>}
          <button className="btn sm" style={{ alignSelf: "flex-start" }} onClick={save}>Save</button>
          <span className="hint">Used on invoices for future payments.</span>
        </div>
      </details>
    </section>
  );
}
