import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { money } from "../lib/format";
import { Card, CardHead, Disclosure, EmptyState, Field, FormActions, FormGrid, Select, Skeleton } from "./kit";

type Inv = { number: string; date: string; total: number; currency: string; supply: string };
type Billing = { name?: string; address?: string; state?: string; gstin?: string; country?: string };

const COUNTRIES = [{ value: "IN", label: "India" }, { value: "US", label: "United States" }, { value: "GB", label: "United Kingdom" },
  { value: "AE", label: "United Arab Emirates" }, { value: "SG", label: "Singapore" }, { value: "XX", label: "Another country" }];

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
    <Card id="invoices">
      <CardHead title="Invoices" />
      {!rows ? <Skeleton label="Loading your invoices" lines={2} /> : rows.length === 0
        ? <EmptyState title="No payments yet">An invoice appears here for every payment.</EmptyState> : (
        <div>{rows.map((r) => (
          <div key={r.number} className="k-line-row">
            <span className="k-line-text"><b className="k-mono">{r.number}</b><span className="k-sub-line">{r.date} · {r.supply}</span></span>
            <span className="k-row"><b>{money(r.total, r.currency, 2)}</b>
              <button type="button" className="btn quiet sm" onClick={() => openInvoice(r.number).catch(fail)}>Open</button></span>
          </div>))}</div>
      )}
      <Disclosure summary={`Details on your invoices${b.gstin ? ` (GSTIN ${b.gstin})` : ""}`}>
        <FormGrid label="Details on your invoices" onSubmit={(e) => { e.preventDefault(); void save(); }}>
          <Field label="Name or business name" value={b.name ?? ""} maxLength={200} onChange={(e) => setB({ ...b, name: e.target.value })} />
          <Field label="Address" value={b.address ?? ""} maxLength={300} onChange={(e) => setB({ ...b, address: e.target.value })} />
          <Field label="Country">{(id) => <Select id={id} value={b.country || "IN"} onChange={(v) => setB({ ...b, country: v })} options={COUNTRIES} />}</Field>
          {india && <Field label="State">{(id) => <Select id={id} value={b.state ?? ""} onChange={(v) => setB({ ...b, state: v })}
            options={[{ value: "", label: "Choose…" }, ...Object.entries(states).map(([c, n]) => ({ value: c, label: n }))]} />}</Field>}
          {india && <Field label="GSTIN" optional info="For businesses, to claim input tax credit." value={b.gstin ?? ""} maxLength={15} onChange={(e) => setB({ ...b, gstin: e.target.value.toUpperCase() })} />}
          <FormActions><button type="submit" className="btn">Save</button><span className="k-note">Used on invoices for future payments.</span></FormActions>
        </FormGrid>
      </Disclosure>
    </Card>
  );
}
