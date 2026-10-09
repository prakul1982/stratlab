import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { openInvoice } from "../../components/InvoicesCard";
import { Card, CardHead, DataTable, Field, FormActions, FormGrid, Select, Skeleton, type Column } from "../../components/kit";
import { useAdmin } from "./AdminContext";

type Seller = { legal_name: string; address: string; state: string; gstin: string; pan: string; lut_arn: string; email: string; prefix: string };
type Row = { number: string; date: string; total: number; currency: string; supply: string; email: string; tax: number };

/** Admin → Money → Invoices: who the invoices are from (GST details) and every invoice of a financial year. */
export function InvoiceAdminPanel() {
  const { fail, notify } = useApp();
  const { reload } = useAdmin();
  const [s, setS] = useState<Seller | null>(null);
  const [states, setStates] = useState<Record<string, string>>({});
  const [rows, setRows] = useState<Row[]>([]);
  const [year, setYear] = useState("");
  const [asked, setAsked] = useState("");
  const load = (y = "") => api<{ seller: Seller; states: Record<string, string>; year: string; invoices: Row[] }>(`/admin/invoices${y ? `?year=${y}` : ""}`)
    .then((x) => { setS(x.seller); setStates(x.states); setYear(x.year); setAsked(x.year); setRows(x.invoices); }).catch(fail);
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const save = async () => {
    try { const x = await api<{ seller: Seller }>("/admin/invoices/seller", { method: "PUT", body: s }); setS(x.seller); notify("Invoice details saved."); void reload(); }
    catch (e) { fail(e); }
  };
  const csv = () => {
    const lines = [["number", "date", "email", "supply", "currency", "total", "tax"].join(",")];
    for (const r of rows) lines.push([r.number, r.date, r.email, r.supply, r.currency, r.total, r.tax].map((x) => `"${String(x ?? "").replace(/"/g, '""')}"`).join(","));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" })); a.download = `stratlab-invoices-${year}.csv`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  };
  const text = (k: keyof Seller, label: string, info?: string) => s && (
    <Field label={label} info={info} value={s[k]} onChange={(e) => setS({ ...s, [k]: e.target.value })} />);
  const cols: Column<Row>[] = [
    { key: "n", header: "Number", rowHeader: true, cell: (r) => <span className="adm-mono">{r.number}</span> },
    { key: "d", header: "Date", cell: (r) => r.date },
    { key: "c", header: "Customer", wrap: true, cell: (r) => r.email },
    { key: "s", header: "Supply", cell: (r) => r.supply },
    { key: "t", header: "Total", numeric: true, cell: (r) => `${r.currency} ${r.total.toFixed(2)}` },
    { key: "g", header: "GST", numeric: true, cell: (r) => r.tax.toFixed(2) },
    { key: "o", header: <span className="sr-only">Open</span>, action: true, cell: (r) => <button type="button" className="btn quiet sm" onClick={() => openInvoice(r.number).catch(fail)}>Open</button> },
  ];
  return (
    <>
      <Card id="invoice-details" label="Invoice details">
        <CardHead title="Invoice details" info="Every payment gets an invoice, numbered per financial year. Prices include GST: 18% split CGST + SGST within your state, IGST across states. Customers outside India are an export of services: zero-rated with your LUT number, otherwise IGST is shown as included. Without a GSTIN the invoice says you aren't registered for GST. Have your accountant confirm the setup." />
        {!s ? <Skeleton label="Loading invoice details" lines={3} /> : (
          <FormGrid label="Who the invoices are from" onSubmit={(e) => { e.preventDefault(); save(); }}>
            {text("legal_name", "Legal name")}
            {text("address", "Address")}
            <Field label="State">{(id) => <Select id={id} value={s.state} onChange={(v) => setS({ ...s, state: v })} options={[{ value: "", label: "Choose…" }, ...Object.entries(states).map(([c, n]) => ({ value: c, label: n }))]} />}</Field>
            {text("gstin", "GSTIN", "Leave empty if not registered for GST.")}
            {text("pan", "PAN")}
            {text("lut_arn", "LUT ARN", "From the Letter of Undertaking filed on the GST portal each year, to export without paying IGST.")}
            {text("email", "Billing email")}
            {text("prefix", "Invoice number prefix", "e.g. SL gives SL/2026-27/0001")}
            <FormActions><button type="submit" className="btn sm">Save details</button></FormActions>
          </FormGrid>
        )}
      </Card>
      <Card label="Invoices">
        <CardHead title={`Invoices, financial year ${year}`}
          actions={<>
            <input className="k-input adm-year" placeholder="2026-27" value={asked} onChange={(e) => setAsked(e.target.value)} aria-label="Financial year"
              onKeyDown={(e) => { if (e.key === "Enter") load(asked.trim()); }} />
            {!!rows.length && <button type="button" className="btn quiet sm" onClick={csv}>Download CSV</button>}
          </>} />
        <p className="k-note k-muted">{rows.length} invoice{rows.length === 1 ? "" : "s"} in this financial year. Type another year and press Enter.</p>
        <DataTable label="Invoices" rows={rows} rowKey={(r) => r.number} columns={cols} empty="No invoices in this financial year yet." />
      </Card>
    </>
  );
}
