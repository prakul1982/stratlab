import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { ago, dateOnly, money } from "../../lib/format";
import { Card, CardHead, DataTable, Disclosure, ErrorState, Notice, Skeleton, StatusList, StatusRow, type Column } from "../../components/kit";
import { useAdmin } from "./AdminContext";
import { invoiceWarning } from "./attention";
import { InvoiceAdminPanel } from "./InvoiceAdminPanel";
import { PricesPanel } from "./PricesPanel";
import { subsSummary } from "./subs";

interface BillingCheck {
  key_id: string; mode: string; secret_length: number; webhook_secret_set: boolean; keys_ok: boolean; keys_error: string | null;
  plans: { label: string; id: string | null; ok: boolean; detail: string | null }[];
  international?: { enabled: boolean | null; info?: boolean; detail: string }; currencies?: string[];
}

type Sub = { id: string; status: string; plan: string | null; plan_id: string | null; created_at: string | null; current_end: string | null; paid_count: number | null;
  /** who it is for (a real user's address, "Test account"), what it charges and how often (LIVE1C-007) */
  user?: string | null; amount?: number | null; currency?: string | null; period?: string | null };
type Refund = { id: string; payment_id: string; amount: number; currency: string; status: string; created_at: string | null };
type Failed = { id: string; amount: number; currency: string; created_at: string | null; why: string | null };
/** Straight from Razorpay (DJ-016, DJ-017), read only: the key's mode, the last webhook, and the newest subscriptions,
 * refunds and failed payments; with the invoices' revenue by month. */
export type Activity = { mode: string; enabled: boolean; last_webhook: { at: string; event: string } | null; currency_plans: string[];
  subscriptions: Sub[]; refunds: Refund[]; failed: Failed[]; errors: Record<string, string>; revenue_by_month?: { month: string; by_currency: Record<string, number> }[] };

const SUBS: Column<Sub>[] = [
  { key: "user", header: "User", rowHeader: true, wrap: true, cell: (x) => (
    <span className="k-stack tight"><span className="adm-break">{x.user ?? "Unknown user"}</span><span className="adm-mono k-muted">{x.id}</span></span>) },
  { key: "plan", header: "Plan", cell: (x) => (x.plan ? x.plan[0].toUpperCase() + x.plan.slice(1) : x.plan_id ?? "–") },
  { key: "amt", header: "Amount", numeric: true, cell: (x) => (x.amount != null ? `${money(x.amount, x.currency ?? "INR")} ${x.period === "year" ? "a year" : "a month"}` : "–") },
  { key: "st", header: "Status", cell: (x) => x.status },
  { key: "made", header: "Started", cell: (x) => dateOnly(x.created_at) },
  { key: "end", header: "Paid to", cell: (x) => dateOnly(x.current_end) },
  { key: "n", header: "Payments", numeric: true, cell: (x) => x.paid_count ?? 0 },
];
const REFUNDS: Column<Refund>[] = [
  { key: "id", header: "Refund", rowHeader: true, cell: (x) => <span className="adm-mono">{x.id}</span> },
  { key: "pay", header: "Payment", cell: (x) => <span className="adm-mono">{x.payment_id}</span> },
  { key: "amt", header: "Amount", numeric: true, cell: (x) => money(x.amount, x.currency, 2) },
  { key: "st", header: "Status", cell: (x) => x.status },
  { key: "at", header: "When", cell: (x) => dateOnly(x.created_at) },
];
const FAILED: Column<Failed>[] = [
  { key: "id", header: "Payment", rowHeader: true, cell: (x) => <span className="adm-mono">{x.id}</span> },
  { key: "amt", header: "Amount", numeric: true, cell: (x) => money(x.amount, x.currency, 2) },
  { key: "why", header: "Why", wrap: true, cell: (x) => x.why ?? "–" },
  { key: "at", header: "When", cell: (x) => dateOnly(x.created_at) },
];

/** The Payments row's facts (DJ-017): the mode, when Razorpay last reached us, and which currencies charge as themselves. */
export function paymentsFacts(a: Activity | null): string {
  if (!a) return "";
  const hook = a.last_webhook?.at ? `last webhook ${ago(a.last_webhook.at)}${a.last_webhook.event ? ` (${a.last_webhook.event})` : ""}` : "no webhook received yet";
  const cur = a.currency_plans.length ? `plans of their own in ${a.currency_plans.join(", ")}` : "every currency charged in rupees";
  return `${a.mode === "live" ? "Live" : a.mode === "test" ? "Test" : "Unknown"} mode · ${hook} · ${cur}`;
}

/** Admin → Money: whether payments work, prices outside India, and invoices. */
export function MoneySection() {
  const { fail } = useApp();
  const { ov } = useAdmin();
  const [check, setCheck] = useState<BillingCheck | null>(null);
  const [busy, setBusy] = useState(false);
  const [act, setAct] = useState<Activity | null>(null);
  const [actFailed, setActFailed] = useState(false);
  useEffect(() => { api<Activity>("/admin/billing/activity").then(setAct).catch((e) => { setActFailed(true); fail(e); }); }, [fail]);
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
          action={{ label: "Fill them in", onClick: () => { document.querySelector("[data-testid='invoice-edit']")?.setAttribute("open", ""); document.getElementById("invoice-details")?.scrollIntoView({ block: "start" }); } }}>
          {empty}
        </Notice>
      )}
      <Card label="Payments">
        <CardHead title="Payments" actions={<button type="button" className="btn quiet sm" disabled={busy} onClick={run}>{busy ? "Asking Razorpay…" : "Check payments setup"}</button>} />
        <StatusList label="Payments">
          <StatusRow state={on ? (act && act.mode === "live" && !act.last_webhook?.at ? "warn" : "ok") : "warn"} label="Razorpay"
            detail={on ? `Connected${act ? ` · ${paymentsFacts(act)}` : ""}${act && act.mode === "live" && !act.last_webhook?.at ? ". Send a test event from Razorpay's dashboard before the first payment: without a webhook a paid plan is not switched on by itself" : ""}` : "Not set up, so paid plans show \"Coming soon\". Grant plans by hand in Users and growth."} />
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
      <Card label="Subscriptions and payments">
        <CardHead title="Subscriptions and payments" info="The newest 50 of each, read from Razorpay now; nothing here changes anything. Revenue by month is from StratLab's own invoices." />
        {!act ? (actFailed ? <ErrorState title="Razorpay couldn't be read" /> : <Skeleton label="Reading Razorpay" lines={3} />)
          : act.errors.all ? <p className="k-small k-muted">{act.errors.all}</p> : (
          <div className="k-stack">
            {!!act.revenue_by_month?.length && (
              <p className="k-small" data-testid="revenue-months"><b>Revenue by month:</b> {act.revenue_by_month.map((m) => `${m.month}: ${Object.entries(m.by_currency).map(([c, v]) => money(v, c)).join(" + ")}`).join(" · ")}</p>
            )}
            <h3 className="adm-sub">Subscriptions ({act.subscriptions.length})</h3>
            {act.errors.subscriptions ? <p className="k-small k-down">{act.errors.subscriptions}</p> : (
              <>
                <p className="k-small" data-testid="subs-summary">{subsSummary(act)}</p>
                <DataTable label="Subscriptions" rows={act.subscriptions.filter((x) => x.status !== "created")} rowKey={(x) => x.id} columns={SUBS} empty="No subscription has been paid yet." stack />
                {act.subscriptions.some((x) => x.status === "created") && (
                  <Disclosure summary={`Show the ${act.subscriptions.filter((x) => x.status === "created").length} unpaid checkouts`} testId="subs-unpaid">
                    <DataTable label="Unpaid checkouts" rows={act.subscriptions.filter((x) => x.status === "created")} rowKey={(x) => x.id} columns={SUBS} stack />
                  </Disclosure>
                )}
              </>
            )}
            <h3 className="adm-sub">Refunds ({act.refunds.length})</h3>
            {act.errors.refunds ? <p className="k-small k-down">{act.errors.refunds}</p>
              : <DataTable label="Refunds" rows={act.refunds} rowKey={(x) => x.id} columns={REFUNDS} empty="No refunds." stack />}
            <h3 className="adm-sub">Failed payments ({act.failed.length})</h3>
            {act.errors.failed ? <p className="k-small k-down">{act.errors.failed}</p>
              : <DataTable label="Failed payments" rows={act.failed} rowKey={(x) => x.id} columns={FAILED} empty="No failed payments among the newest 100." stack />}
          </div>
        )}
      </Card>
      <PricesPanel />
      <InvoiceAdminPanel />
    </>
  );
}
