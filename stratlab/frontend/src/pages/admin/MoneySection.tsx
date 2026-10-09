import { useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { Card, CardHead, Notice, StatusList, StatusRow } from "../../components/kit";
import { useAdmin } from "./AdminContext";
import { invoiceWarning } from "./attention";
import { InvoiceAdminPanel } from "./InvoiceAdminPanel";
import { PricesPanel } from "./PricesPanel";

interface BillingCheck {
  key_id: string; mode: string; secret_length: number; webhook_secret_set: boolean; keys_ok: boolean; keys_error: string | null;
  plans: { label: string; id: string | null; ok: boolean; detail: string | null }[];
  international?: { enabled: boolean | null; info?: boolean; detail: string }; currencies?: string[];
}

/** Admin → Money: whether payments work, prices outside India, and invoices. */
export function MoneySection() {
  const { fail } = useApp();
  const { ov } = useAdmin();
  const [check, setCheck] = useState<BillingCheck | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try { setCheck(await api<BillingCheck>("/admin/billing/check", { method: "POST" })); } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const on = !!ov?.server.billing_enabled;
  const empty = invoiceWarning(ov?.server.invoice_seller);        // R7M-001: the first invoice would contradict the Plans page
  return (
    <>
      {empty && (
        <Notice tone="warn" role="status" label="Invoice seller details" className="adm-invoice-warning"
          action={{ label: "Fill them in", onClick: () => document.getElementById("invoice-details")?.scrollIntoView({ block: "start" }) }}>
          {empty}
        </Notice>
      )}
      <Card label="Payments">
        <CardHead title="Payments" actions={<button type="button" className="btn quiet sm" disabled={busy} onClick={run}>{busy ? "Asking Razorpay…" : "Check payments setup"}</button>} />
        <StatusList label="Payments">
          <StatusRow state={on ? "ok" : "warn"} label="Razorpay" detail={on ? "Connected" : "Not set up, so paid plans show \"Coming soon\". Grant plans by hand in Users and growth."} />
          {check && <>
            <StatusRow state={check.keys_ok ? "ok" : "bad"} label={`Keys (${check.mode} mode)`}
              detail={check.keys_ok ? `Razorpay accepts key ${check.key_id}` : `Key ${check.key_id}, secret ${check.secret_length} characters: ${check.keys_error}. Regenerate the key in Razorpay and paste BOTH the new Key ID and secret into Railway.`} />
            {check.plans.map((p) => <StatusRow key={p.label} state={p.ok ? "ok" : p.id ? "bad" : "warn"} label={p.label} detail={p.detail ?? ""} />)}
            <StatusRow state={check.webhook_secret_set ? "ok" : "bad"} label="Webhook secret" detail={check.webhook_secret_set ? "Set" : "RAZORPAY_WEBHOOK_SECRET is missing"} />
            {check.international && <StatusRow state={check.international.enabled === true ? "ok" : check.international.info ? "warn" : check.international.enabled === false ? "bad" : "warn"}
              label="International cards" detail={`${check.international.detail}${check.currencies?.length ? ` Plans are priced in ${check.currencies.join(", ")}.` : ""}`} />}
          </>}
        </StatusList>
      </Card>
      <PricesPanel />
      <InvoiceAdminPanel />
    </>
  );
}
