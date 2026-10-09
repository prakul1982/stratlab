import { useState } from "react";
import { Card, CardHead, ConfirmDialog, DataTable, Field, FieldGroup, FormGrid, Notice, PageHeader, Select, Seg, type Column } from "../components/kit";
import { Link } from "react-router-dom";
import { LegalLinks } from "../components/LegalLinks";
import { api, loadRazorpay } from "../lib/api";
import { useApp } from "../lib/app";
import { dateOnly } from "../lib/format";
import { aboutMoney, approx, chargedLine, money, rupeesNote, usePricing } from "../lib/currency";
import { PromoCountdown } from "../components/PromoCountdown";
import { PlanInterestButton } from "../components/PlanInterest";
import { track } from "../lib/analytics";
import { EVERYONE, FEATURES, FLAGS, LIMITS, NUMBERS, PRICE, WHO, type Limits, type PlanId } from "../lib/plans";
import { readViewAs } from "../lib/viewAs";
import { canBuy, finePrint, paymentWindowLine, pricingIntro, rupeeCharge, viewingPlansNote, YEARLY_LABEL, yearlySaving } from "../lib/offer";

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
  const groups: { id: string; title: string; rows: Row[] }[] = [
    { id: "limits", title: "How much", rows: NUMBERS.map(([k, label]) => ({ id: String(k), label, cell: (p: PlanId) => num(p, k) })) },
    { id: "paid", title: "What each plan adds", rows: FLAGS.map(([f, label]) => ({ id: String(f), label, cell: (p: PlanId) => (lim(p).features.includes(f) ? "✓" : "–") })) },
    { id: "all", title: "On every plan", rows: EVERYONE.map((label) => ({ id: label, label, cell: () => "✓" })) },
  ];
  const columns = (first: string): Column<Row>[] => [
    { key: "label", header: first, wrap: true, cell: (r) => r.label },
    ...ids.map((p) => ({ key: p, header: names[p], numeric: true, cell: (r: Row) => r.cell(p) })),
  ];
  // one table per group, each with the plan names on top; the header stays in view as the page scrolls past it
  return (
    <Card id="compare">
      <CardHead title="Side by side" />
      {groups.map((g) => (
        <div key={g.id} className="k-stack" data-plans-group={g.id}>
          <h3 className="k-sub">{g.title}</h3>
          <DataTable label={`Plans side by side: ${g.title.toLowerCase()}`} columns={columns(g.title)} rows={g.rows} rowKey={(r) => r.id} pinHead />
        </div>
      ))}
    </Card>
  );
}

const planName = (p: PlanId) => ({ free: "Free", basic: "Basic", pro: "Pro" }[p]);

export function PlansPage() {
  const { me, fail, notify, refreshMe, viewAs: viewAsMe } = useApp();
  // "View as" from /me once it has answered, and from this device's own choice before then: the page draws the buy
  // buttons from the public prices while /me is still on its way, and they must already be off (R7M-010, again in R8)
  const viewAs = me ? viewAsMe : readViewAs();
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
  // GST is spoken of only while the invoices carry it (the seller's GSTIN is set in Admin → Money): an invoice with no GSTIN
  // says the supplier isn't registered and charges none, so "incl. GST" and "a GST invoice" would contradict it (R7M-001)
  const gst = pricing?.invoice?.gst === true;
  const rupees = (p: PlanId, per: string) => {
    const sp = me?.plans?.[p];
    return sp ? (per === "year" ? sp.price_year : sp.price) : PRICE[p][per === "year" ? 1 : 0];
  };
  /** The price shown in the visitor's currency, and the one their card is charged (rupees until that currency's plans exist). */
  const priceOf = (p: PlanId, per: string) => {
    if (p === "free" && row) return { shown: money(row, 0, currency), charged: null as string | null, inr: false, about: null as string | null };
    if (p === "free" || !row || currency === "INR") return { shown: `₹${rupees(p, per).toLocaleString("en-IN")}`, charged: null as string | null, inr: p !== "free", about: null as string | null };
    const local = (row as unknown as Record<string, number>)[per === "year" ? `${p}_year` : p];
    const chargedIn = per === "year" ? row.yearly_charged_in : row.charged_in;
    // the admin table's price ($8 and $20 for dollars); "Charged as ₹…" under it while that currency is charged in rupees
    // a converted amount says so ("≈ SAR 27") beside the rupee charge it comes from (R7O-008); a fixed price (dollars,
    // euros, pounds) says what that rupee charge is in its currency today (R8O-006)
    const aboutV = chargedIn === "INR" ? row.charge_about?.[(per === "year" ? `${p}_year` : p) as "basic" | "pro" | "basic_year" | "pro_year"] : undefined;
    return { shown: approx(row, chargedIn) + money(row, local, currency), charged: chargedIn === "INR" ? money(inr, rupees(p, per), "INR") : null, inr: false,
      about: aboutV != null ? aboutMoney(row, aboutV, currency) : null };
  };
  /** What a year saves against twelve months, in the price's own currency (Pro's year is ₹9 over ten months, so each card says its own number). */
  const savingOf = (p: "basic" | "pro") => {
    const foreign = !!row && currency !== "INR";
    const month = foreign ? (row as unknown as Record<string, number>)[p] : rupees(p, "month");
    const year = foreign ? (row as unknown as Record<string, number>)[`${p}_year`] : rupees(p, "year");
    const save = yearlySaving(month, year);
    return save == null ? null : money(foreign ? row : inr, save, foreign ? currency : "INR");
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
        // the payment window's name carries the plan and the period (R6V-009)
        key: d.key_id, subscription_id: d.subscription_id, name: `StratLab · ${planName(plan)}, ${period === "year" ? "yearly" : "monthly"}`,
        notes: { plan, period },
        description: `${plan === "pro" ? "Pro" : "Basic"} plan, ${d.currency === "INR" ? `₹${rupees(plan, period).toLocaleString("en-IN")}${gst ? " incl. GST" : ""}` : priceOf(plan, period).shown} / ${period}`,
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
  // every purchase is confirmed on this page first, with the plan, the period, the amount charged and the renewal (R6V-009)
  const ask = (plan: "basic" | "pro") => setSwitching(plan);
  const given = !!me?.billing?.given_by_owner;
  const RANK: Record<PlanId, number> = { free: 0, basic: 1, pro: 2 };
  /** What the card is charged, in words: "₹699 incl. 18% GST, every month". */
  const chargeWords = (p: "basic" | "pro") => {
    const rs = rupeeCharge(rupees(p, period), gst);
    const shown = priceOf(p, period);
    return `${rs}${shown.charged || currency === "INR" ? "" : ` (shown as ${shown.shown})`}, every ${period}`;
  };

  return (
    <div className="k-page">
      <PageHeader eyebrow="Account · Plans" title="Plans"
        lede={intro.lede}
        actions={<Link to="/account" className="btn quiet sm">← Account</Link>} />
      <PromoCountdown plansLink={false} />
      {!billing && me && (
        <Notice label="Paid plans aren't on sale yet" actions={<PlanInterestButton source="plans" />}>
          Basic and Pro aren't on sale yet. Press the button and we'll tell you the day they open.
        </Notice>
      )}
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
                options={[{ value: "month", label: "Monthly" }, { value: "year", label: YEARLY_LABEL }]} />
            </FieldGroup>
          )}
        </FormGrid>
      )}
      {viewAs && billing && <div id="plans-viewas" data-testid="plans-viewas"><Notice tone="warn" role="status">{viewingPlansNote(planName(viewAs))}</Notice></div>}
      {anyRupees && billing && <Notice>{rupeesNote(currency, priceOf("basic", period).about && priceOf("pro", period).about
        ? { basic: priceOf("basic", period).about as string, pro: priceOf("pro", period).about as string } : null)}</Notice>}
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
                <div className="k-plan-price">{price.shown}<span> / {period}</span></div>
                {price.inr && gst && <span className="k-note">incl. GST</span>}
                {period === "year" && p !== "free" && savingOf(p) && <span className="k-note">Saves {savingOf(p)} a year against paying monthly</span>}
                {price.charged && <span className="k-note" data-testid={`charged-${p}`}>{billing ? chargedLine(price.charged, gst, period, price.about) : `${price.charged} a ${period} in India${gst ? ", incl. GST" : ""}`}</span>}
              </div>
              <ul className="k-plan-list">
                {FEATURES[p].map((f) => f.endsWith(":") ? <li key={f} className="head">{f}</li> : <li key={f}><span aria-hidden="true">✓</span>{f}</li>)}
              </ul>
              {cur ? <button className="btn outline" disabled>Current plan</button>
                : p === "free" ? <span className="k-small k-muted">Included whenever a paid plan ends</span>
                  : !billing ? <span className="lp-plan-note k-small k-muted">Opens soon</span>
                    // a plan the owner gave already includes everything below it: nothing to buy there (R6V-009)
                    : given && paid && RANK[p] <= RANK[paid as PlanId] ? <span className="k-small k-muted" data-testid="plan-included">Included in the {planName(paid as PlanId)} plan you were given</span>
                    : <button className={`btn ${p === "pro" ? "" : "outline"}`} disabled={!!busy || !!viewAs} onClick={() => ask(p)}
                      title={viewAs ? viewingPlansNote(planName(viewAs)) : undefined} aria-describedby={viewAs ? "plans-viewas" : undefined}>
                      {busy === p ? "Opening checkout…" : paid === "pro" && p === "basic" ? "Switch to Basic" : `Upgrade to ${planName(p)}`}
                      {viewAs && <span className="k-small"> (off while viewing as {planName(viewAs)})</span>}</button>}
            </Card>
          );
        })}
      </div>
      <Compare plans={me?.plans as Record<string, Partial<Limits>> | undefined} />
      {me && paid !== "free" && me.billing.renews_or_ends && (
        <p className="k-small k-muted">{me.billing.cancel_at_period_end ? "Ends" : "Renews"} on {dateOnly(me.billing.renews_or_ends)}.</p>
      )}
      {billing ? (
        <p className="k-small k-muted k-measure">{gst ? "Rupee prices include 18% GST, and every payment gets a GST invoice in Account." : "Every payment gets an invoice in Account."} Paid plans renew automatically each month or year until you cancel, which you can do any time from Account. By subscribing you agree to the <Link className="link" to="/terms">terms</Link> and the <Link className="link" to="/refunds">cancellation and refund policy</Link>. Payments are handled securely by our payment partner.</p>
      ) : (
        <p className="k-small k-muted k-measure">{finePrint(offer, { currency: row && currency !== "INR" ? currency : "INR", inRupees: row?.charged_in === "INR", inRupeesYear: row?.yearly_charged_in === "INR",
          charged: { basic: `₹${rupees("basic", "month").toLocaleString("en-IN")}`, pro: `₹${rupees("pro", "month").toLocaleString("en-IN")}` }, gst }).join(" ")}</p>
      )}
      <p className="k-small k-muted k-measure">StratLab is a research and paper trading tool. It doesn't place real orders or give investment advice, and past results don't predict future returns.</p>
      <LegalLinks />
      {switching && (
        <ConfirmDialog title={paid !== "free" && me ? `Switch to ${planName(switching)}?` : `Subscribe to ${planName(switching)}?`}
          confirmLabel="Continue to payment" danger={false}
          onClose={() => setSwitching(null)} onConfirm={() => { const p = switching; setSwitching(null); void subscribe(p); }}>
          <span data-testid="plan-confirm">
            {planName(switching)} plan, billed {period === "year" ? "yearly" : "monthly"}: {chargeWords(switching)}. It renews automatically
            each {period} until you cancel, any time from Account. {paymentWindowLine(planName(switching), period)}
            {paid !== "free" && me && !given ? " Your current subscription stops billing once the new one is active." : ""}
          </span>
        </ConfirmDialog>
      )}
    </div>
  );
}
