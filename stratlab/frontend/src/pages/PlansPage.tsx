import { useState } from "react";
import { Card, CardHead, ConfirmDialog, DataTable, Field, FieldGroup, FormGrid, Notice, PageHeader, Select, Seg, type Column } from "../components/kit";
import { Link } from "react-router-dom";
import { LegalLinks } from "../components/LegalLinks";
import { api, loadRazorpay } from "../lib/api";
import { useApp } from "../lib/app";
import { dateOnly } from "../lib/format";
import { money, usePricing } from "../lib/currency";
import { PromoCountdown } from "../components/PromoCountdown";
import { track } from "../lib/analytics";
import { EVERYONE, FEATURES, FLAGS, LIMITS, NUMBERS, PRICE, WHO, type Limits, type PlanId } from "../lib/plans";
import { canBuy, finePrint, pricingIntro } from "../lib/offer";

/** Every limit and feature side by side, from the server's plans when signed in. */
function Compare({ plans }: { plans?: Record<string, Partial<Limits>> }) {
  const lim = (p: PlanId): Limits => ({ ...LIMITS[p], ...(plans?.[p] ?? {}) });
  const num = (p: PlanId, k: keyof Limits) => {
    const v = lim(p)[k] as number | null;
    return v == null ? "Unlimited" : p === "free" && k === "live_limit" ? `${v}, for 5 market days` : v.toLocaleString("en-IN");
  };
  const ids: PlanId[] = ["free", "basic", "pro"];
  const names = { free: "Free", basic: "Basic", pro: "Pro" };
  type Row = { id: string; label: string; cell: (p: PlanId) => string };
  const rows: Row[] = [
    ...NUMBERS.map(([k, label]) => ({ id: String(k), label, cell: (p: PlanId) => num(p, k) })),
    ...FLAGS.map(([f, label]) => ({ id: String(f), label, cell: (p: PlanId) => (lim(p).features.includes(f) ? "✓" : "–") })),
    ...EVERYONE.map((label) => ({ id: label, label, cell: () => "✓" })),
  ];
  const columns: Column<Row>[] = [
    { key: "label", header: "Backtests, research and paper trading", wrap: true, cell: (r) => r.label },
    ...ids.map((p) => ({ key: p, header: names[p], numeric: true, cell: (r: Row) => r.cell(p) })),
  ];
  return (
    <Card id="compare">
      <CardHead title="Side by side" />
      <DataTable label="Plans side by side" columns={columns} rows={rows} rowKey={(r) => r.id} />
    </Card>
  );
}

export function PlansPage() {
  const { me, fail, notify, refreshMe } = useApp();
  const [busy, setBusy] = useState<string | null>(null);
  const { pricing, currency, pick } = usePricing();
  // one answer for what's on sale today (plans.offer_state): /me's, else the public one the landing page reads
  const offer = me?.offer ?? pricing?.offer ?? null;
  const billing = offer ? canBuy(offer) : me?.billing_enabled !== false;
  const yearlyOk = offer ? offer.yearly : !!me?.yearly_enabled;
  const intro = pricingIntro(offer, LIMITS.pro, "app");
  const [yearly, setYearly] = useState(false);
  const period = yearly && yearlyOk ? "year" : "month";
  const paid = me?.paid_plan ?? me?.plan;   // me.plan is Pro for everyone during the launch offer
  const row = pricing?.currencies[currency];
  const inr = pricing?.currencies.INR;
  const rupees = (p: PlanId, per: string) => {
    const sp = me?.plans?.[p];
    return sp ? (per === "year" ? sp.price_year : sp.price) : PRICE[p][per === "year" ? 1 : 0];
  };
  /** The price shown in the visitor's currency, and the one their card is charged (rupees until that currency's plans exist). */
  const priceOf = (p: PlanId, per: string) => {
    if (p === "free" && row) return { shown: money(row, 0, currency), charged: null as string | null, inr: false };
    if (p === "free" || !row || currency === "INR") return { shown: `₹${rupees(p, per).toLocaleString("en-IN")}`, charged: null as string | null, inr: p !== "free" };
    const local = (row as unknown as Record<string, number>)[per === "year" ? `${p}_year` : p];
    const chargedIn = per === "year" ? row.yearly_charged_in : row.charged_in;
    // charged in rupees: the amount is the rupee price at today's rate, so it says "about"
    const about = chargedIn === "INR" && (per === "year" ? row.approx_year : row.approx) !== false;
    return { shown: `${about ? "about " : ""}${money(row, local, currency)}`, charged: chargedIn === "INR" ? money(inr, rupees(p, per), "INR") : null, inr: false };
  };
  const anyRupees = currency !== "INR" && !!row && (period === "year" ? row.yearly_charged_in : row.charged_in) === "INR";

  const subscribe = async (plan: "basic" | "pro") => {
    track("upgrade clicked", { plan, period, source: "plans" });
    setBusy(plan);
    try {
      const d = await api<{ subscription_id: string; key_id: string; email: string; currency: string }>("/billing/subscribe", { method: "POST", body: { plan, period, currency } });
      await loadRazorpay();
      track("checkout started", { plan, period });
      const rz = new window.Razorpay({
        key: d.key_id, subscription_id: d.subscription_id, name: "StratLab",
        description: `${plan === "pro" ? "Pro" : "Basic"} plan, ${d.currency === "INR" ? `₹${rupees(plan, period).toLocaleString("en-IN")} incl. GST` : priceOf(plan, period).shown} / ${period}`,
        prefill: { email: d.email || "" }, theme: { color: "#1D1B17" },
        handler: async (resp: unknown) => {
          try { await api("/billing/verify", { method: "POST", body: resp }); await refreshMe(); notify(`You're on ${plan === "pro" ? "Pro" : "Basic"} now.`); }
          catch (e) { fail(e); }
          finally { setBusy(null); }
        },
        modal: { ondismiss: () => setBusy(null) },
      });
      rz.on("payment.failed", (r: { error: { description: string } }) => { notify(`Payment failed: ${r.error.description}`); setBusy(null); });
      rz.open();
    } catch (e) { fail(e); setBusy(null); }
  };

  const [switching, setSwitching] = useState<"basic" | "pro" | null>(null);
  const planName = (p: PlanId) => ({ free: "Free", basic: "Basic", pro: "Pro" }[p]);
  const ask = (plan: "basic" | "pro") => (me && paid !== "free" ? setSwitching(plan) : void subscribe(plan));

  return (
    <div className="k-page">
      <PageHeader eyebrow="Account · Plans" title="Plans"
        lede={intro.lede}
        actions={<Link to="/account" className="btn quiet sm">← Account</Link>} />
      <PromoCountdown plansLink={false} />
      {(pricing || (billing && yearlyOk)) && (
        <FormGrid label="Price options">
          {pricing && (
            <Field label="Prices in">
              {(id) => <Select id={id} value={currency} onChange={pick} options={Object.entries(pricing.currencies).map(([c, r]) => ({ value: c, label: `${c} · ${r.name}` }))} />}
            </Field>
          )}
          {billing && yearlyOk && (
            <FieldGroup label="Billed">
              <Seg label="Billing period" value={yearly ? "year" : "month"} onChange={(v) => setYearly(v === "year")}
                options={[{ value: "month", label: "Monthly" }, { value: "year", label: "Yearly · 2 months free" }]} />
            </FieldGroup>
          )}
        </FormGrid>
      )}
      {anyRupees && billing && <Notice>Paid in rupees for now: your card is charged the rupee price shown under each plan and your bank converts it, so the amount in {currency} can differ slightly.</Notice>}
      <div className="k-plans">
        {(["free", "basic", "pro"] as const).map((p) => {
          const cur = paid === p;
          const price = priceOf(p, period);
          return (
            <Card key={p} className={p === "pro" ? "k-plan pro" : "k-plan"}>
              <div className="k-stack tight">
                <h2 className="k-card-title">{planName(p)}</h2>
                <span className="k-small k-muted">{WHO[p]}</span>
              </div>
              <div className="k-stack tight">
                <div className="k-plan-price">{price.shown.startsWith("about ") ? <><span>about </span>{price.shown.slice(6)}</> : price.shown}<span> / {period}</span></div>
                {price.inr && <span className="k-note">incl. GST</span>}
                {price.charged && <span className="k-note">Charged as {price.charged} incl. GST / {period}</span>}
              </div>
              <ul className="k-plan-list">
                {FEATURES[p].map((f) => f.endsWith(":") ? <li key={f} className="head">{f}</li> : <li key={f}><span aria-hidden="true">✓</span>{f}</li>)}
              </ul>
              {cur ? <button className="btn outline" disabled>Current plan</button>
                : p === "free" ? <span className="k-small k-muted">Included whenever a paid plan ends</span>
                  : !billing ? <span className="lp-plan-note k-small k-muted">Not on sale yet</span>
                    : <button className={`btn ${p === "pro" ? "" : "outline"}`} disabled={!!busy} onClick={() => ask(p)}>
                      {busy === p ? "Opening checkout…" : paid === "pro" && p === "basic" ? "Switch to Basic" : `Upgrade to ${planName(p)}`}</button>}
            </Card>
          );
        })}
      </div>
      <Compare plans={me?.plans as Record<string, Partial<Limits>> | undefined} />
      {me && paid !== "free" && me.billing.renews_or_ends && (
        <p className="k-small k-muted">{me.billing.cancel_at_period_end ? "Ends" : "Renews"} on {dateOnly(me.billing.renews_or_ends)}.</p>
      )}
      {billing ? (
        <p className="k-small k-muted k-measure">Rupee prices include 18% GST, and every payment gets a GST invoice in Account. Paid plans renew automatically each month or year until you cancel, which you can do any time from Account. By subscribing you agree to the <Link className="link" to="/terms">terms</Link> and the <Link className="link" to="/refunds">cancellation and refund policy</Link>. Payments are handled securely by our payment partner.</p>
      ) : (
        <p className="k-small k-muted k-measure">{finePrint(offer, { currency: row && currency !== "INR" ? currency : "INR", approx: !!row?.approx, approxYear: !!row?.approx_year,
          charged: { basic: `₹${rupees("basic", "month").toLocaleString("en-IN")}`, pro: `₹${rupees("pro", "month").toLocaleString("en-IN")}` } }).join(" ")}</p>
      )}
      <p className="k-small k-muted k-measure">StratLab is a research and paper trading tool. It doesn't place real orders or give investment advice, and past results don't predict future returns.</p>
      <LegalLinks />
      {switching && (
        <ConfirmDialog title={`Switch to ${planName(switching)}?`} confirmLabel={`Switch to ${planName(switching)}`} danger={false}
          onClose={() => setSwitching(null)} onConfirm={() => { const p = switching; setSwitching(null); void subscribe(p); }}>
          Your current subscription stops billing once the new one is active.
        </ConfirmDialog>
      )}
    </div>
  );
}
