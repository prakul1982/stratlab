import { useState } from "react";
import { AccountWait } from "../components/AccountWait";
import { Card, ConfirmDialog, Field, FieldGroup, FormGrid, Notice, PageHeader, Select, Seg } from "../components/kit";
import { Link } from "react-router-dom";
import { LegalLinks } from "../components/LegalLinks";
import { api, loadRazorpay } from "../lib/api";
import { useApp } from "../lib/app";
import { dateOnly } from "../lib/format";
import { aboutLine, aboutMoney, chargedInRupees, money, rupeesNote, usePricing } from "../lib/currency";
import { PromoCountdown } from "../components/PromoCountdown";
import { PlanCompare } from "../components/PlanCompare";
import { PlanInterestButton } from "../components/PlanInterest";
import { track } from "../lib/analytics";
import { FEATURES, LIMITS, PRICE, WHO, type Limits, type PlanId } from "../lib/plans";
import { readViewAs } from "../lib/viewAs";
import { canBuy, chargeAboutNote, checkoutDescription, finePrint, paymentWindowLine, pricingIntro, rupeeCharge, switchEndsNote, viewingPlansNote, YEARLY_LABEL, yearlySaving } from "../lib/offer";

const planName = (p: PlanId) => ({ free: "Free", basic: "Basic", pro: "Pro" }[p]);

export function PlansPage() {
  const { me, session, ready, fail, notify, refreshMe, viewAs: viewAsMe } = useApp();
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
  /** The price a card shows as its main price, and the one it is charged. A card charged in rupees shows the rupee price, with the
   * visitor's currency only as "about $7 at today's rate" beside it (DK-001); a currency with its own plan shows its fixed price. */
  const priceOf = (p: PlanId, per: string) => {
    const none = { charged: null as string | null, inr: false, about: null as string | null, aside: null as string | null };
    if (p === "free" && row) return { ...none, shown: money(row, 0, currency) };
    if (p === "free" || !row || currency === "INR") return { ...none, shown: `₹${rupees(p, per).toLocaleString("en-IN")}`, inr: p !== "free" };
    const field = (per === "year" ? `${p}_year` : p) as "basic" | "pro" | "basic_year" | "pro_year";
    const local = (row as unknown as Record<string, number>)[field];
    const chargedIn = per === "year" ? row.yearly_charged_in : row.charged_in;
    if (!chargedInRupees(row, currency, chargedIn)) return { ...none, shown: money(row, local, currency) };
    // the admin table's amount, rounded to a whole unit, is what the rupee charge is in the visitor's currency today (R7O-008, R8O-006)
    const aboutV = row.charge_about?.[field] ?? (row.converted ? local : undefined);
    const charged = money(inr, rupees(p, per), "INR");
    return { shown: charged, charged, inr: true, about: aboutV != null ? aboutMoney(row, aboutV, currency) : null, aside: aboutLine(row, currency, field) };
  };
  /** What a year saves against twelve months, in the price's own currency (Pro's year is ₹9 over ten months, so each card says its own number). */
  const savingOf = (p: "basic" | "pro") => {
    const foreign = !!row && currency !== "INR" && !chargedInRupees(row, currency, period === "year" ? row.yearly_charged_in : row.charged_in);
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
        description: checkoutDescription(plan === "pro" ? "Pro" : "Basic", period),
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
    const shown = priceOf(p, period);
    // a currency with its own Razorpay plan is charged in that currency: its amount, no rupees or GST
    const own = row && currency !== "INR" && (period === "year" ? row.yearly_charged_in : row.charged_in) === currency;
    if (own) return `${money(row, (row as unknown as Record<string, number>)[period === "year" ? `${p}_year` : p], currency)}, every ${period}`;
    const rs = rupeeCharge(rupees(p, period), gst);
    // charged in rupees from another currency's card: the dialog says what that is there today ("₹699 (about $7.23 today)")
    return `${rs}${chargeAboutNote(!!shown.charged, shown.shown, shown.about)}${shown.charged || currency === "INR" ? "" : ` (shown as ${shown.shown})`}, every ${period}`;
  };

  const ownCurrency = row && currency !== "INR" && (period === "year" ? row.yearly_charged_in : row.charged_in) === currency ? currency : undefined;

  // signed in: hold until the account has answered, so the signed-out page is never drawn for someone who is signed in
  if (!ready || (session && !me)) return <div className="k-page"><PageHeader eyebrow="Account · Plans" title="Plans" /><Card label="Loading plans"><AccountWait label="Loading plans" /></Card></div>;
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
                <div className="k-plan-price">{price.shown}<span>{p === "free" ? " always" : ` / ${period}`}</span></div>
                {price.aside && <span className="k-note" data-testid={`about-${p}`}>{price.aside}</span>}
                {price.inr && gst && <span className="k-note">incl. GST</span>}
                {period === "year" && p !== "free" && savingOf(p) && <span className="k-note">Saves {savingOf(p)} a year against paying monthly</span>}
              </div>
              <ul className="k-plan-list">
                {FEATURES[p].map((f) => f.endsWith(":") ? <li key={f} className="head">{f}</li> : <li key={f}><span aria-hidden="true">✓</span>{f}</li>)}
              </ul>
              {cur ? <button className="btn outline" disabled>Current plan</button>
                : p === "free" ? <span className="k-small k-muted">Included whenever a paid plan ends</span>
                  // the current plan isn't known until /me answers: no "Upgrade to Pro" for a Pro reader meanwhile
                  : !me ? <button className="btn outline" disabled>Checking your plan…</button>
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
      {anyRupees && billing && <Notice>{rupeesNote(currency, priceOf("basic", period).about && priceOf("pro", period).about
        ? { basic: priceOf("basic", period).about as string, pro: priceOf("pro", period).about as string } : null)}</Notice>}
      <PlanCompare plans={me?.plans as Record<string, Partial<Limits>> | undefined} />
      {me && paid !== "free" && me.billing.renews_or_ends && (
        <p className="k-small k-muted">{me.billing.cancel_at_period_end ? "Ends" : "Renews"} on {dateOnly(me.billing.renews_or_ends)}.</p>
      )}
      {billing ? (
        <p className="k-small k-muted k-measure">{gst ? "Rupee prices include 18% GST, and every payment gets a GST invoice in Account." : "The price shown is all you pay: no GST is added. Every payment gets an invoice in Account."} Paid plans renew automatically each month or year until you cancel, which you can do any time from Account. By subscribing you agree to the <Link className="link" to="/terms">terms</Link> and the <Link className="link" to="/refunds">cancellation and refund policy</Link>. Payments are handled securely by our payment partner.</p>
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
            each {period} until you cancel, any time from Account. {paymentWindowLine(planName(switching), period, ownCurrency)}
            {paid !== "free" && me && !given ? ` ${switchEndsNote(planName(paid as PlanId))}` : ""}
          </span>
        </ConfirmDialog>
      )}
    </div>
  );
}
