import { useState } from "react";
import { AccountWait } from "../components/AccountWait";
import { Card, ConfirmDialog, FieldGroup, FormGrid, Notice, PageHeader, Seg } from "../components/kit";
import { Link } from "react-router-dom";
import { LegalLinks } from "../components/LegalLinks";
import { api, loadRazorpay } from "../lib/api";
import { useApp } from "../lib/app";
import { dateOnly } from "../lib/format";
import { aboutUsd, usdNote, usePricing } from "../lib/currency";
import { PromoCountdown } from "../components/PromoCountdown";
import { PlanCompare } from "../components/PlanCompare";
import { PlanInterestButton } from "../components/PlanInterest";
import { track } from "../lib/analytics";
import { FEATURES, LIMITS, PRICE, splitFeatures, WHO, type Limits, type PlanId } from "../lib/plans";
import { readViewAs } from "../lib/viewAs";
import { canBuy, checkoutDescription, finePrint, paymentWindowLine, pricingIntro, rupeeCharge, switchEndsNote, viewingPlansNote, YEARLY_LABEL, yearlySaving } from "../lib/offer";

const planName = (p: PlanId) => ({ free: "Free", basic: "Basic", pro: "Pro" }[p]);

export function PlansPage() {
  const { me, session, ready, fail, notify, refreshMe, viewAs: viewAsMe } = useApp();
  // "View as" from /me once it has answered, and from this device's own choice before then: the page draws the buy
  // buttons from the public prices while /me is still on its way, and they must already be off (R7M-010, again in R8)
  const viewAs = me ? viewAsMe : readViewAs();
  const [busy, setBusy] = useState<string | null>(null);
  // item 34 (owner, 29 Oct): rupees first, the currency every card is charged in, with "about $" beside each price; no currency
  // picker and no browser locale that shows dollars alone (LIVE1B-067/078)
  const { pricing, rate } = usePricing();
  // one answer for what's on sale today (plans.offer_state): /me's, else the public one the landing page reads
  const offer = me?.offer ?? pricing?.offer ?? null;
  const billing = offer ? canBuy(offer) : me?.billing_enabled !== false;
  const yearlyOk = offer ? offer.yearly : !!me?.yearly_enabled;
  const intro = pricingIntro(offer, LIMITS.pro, "app");
  const [yearly, setYearly] = useState(false);
  const period = yearly && yearlyOk ? "year" : "month";
  const paid = me?.paid_plan ?? me?.plan;   // me.plan is Pro for everyone during the launch offer
  // GST is spoken of only while the invoices carry it (the seller's GSTIN is set in Admin → Money): an invoice with no GSTIN
  // says the supplier isn't registered and charges none, so "incl. GST" and "a GST invoice" would contradict it (R7M-001)
  const gst = pricing?.invoice?.gst === true;
  const rupees = (p: PlanId, per: string) => {
    const sp = me?.plans?.[p];
    return sp ? (per === "year" ? sp.price_year : sp.price) : PRICE[p][per === "year" ? 1 : 0];
  };
  /** A card's price: the rupee amount it is charged, and the dollar figure beside it ("about $8"); Free is "₹0", no dollars. */
  const priceOf = (p: PlanId, per: string) => {
    const inr = p === "free" ? 0 : rupees(p, per);
    return { shown: `₹${inr.toLocaleString("en-IN")}`, inr: p !== "free", about: inr > 0 ? aboutUsd(inr, rate) : null };
  };
  /** What a year saves against twelve months, in rupees with its dollar figure. */
  const savingOf = (p: "basic" | "pro") => {
    const save = yearlySaving(rupees(p, "month"), rupees(p, "year"));
    return save == null ? null : `₹${save.toLocaleString("en-IN")} (${aboutUsd(save, rate)})`;
  };

  const subscribe = async (plan: "basic" | "pro") => {
    track("upgrade clicked", { plan, period, source: "plans" });
    setBusy(plan);
    try {
      // always the rupee plan: Razorpay charges rupees exactly as before (item 34 changed only what the page shows)
      const d = await api<{ subscription_id: string; key_id: string; email: string; currency: string }>("/billing/subscribe", { method: "POST", body: { plan, period, currency: "INR" } });
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
  /** What the card is charged, in words: "₹699 incl. 18% GST (about $8), every month". */
  const chargeWords = (p: "basic" | "pro") => `${rupeeCharge(rupees(p, period), gst)} (${aboutUsd(rupees(p, period), rate)}), every ${period}`;

  /** The amount charged, alone, for the dialog's button (LIVE1B-079: "Continue to payment" did not say what it would charge). */
  const chargeAmount = (p: "basic" | "pro") => rupeeCharge(rupees(p, period), gst);

  // signed in: hold until the account has answered, so the signed-out page is never drawn for someone who is signed in
  if (!ready || (session && !me)) return <div className="k-page"><PageHeader eyebrow="Account · Plans" title="Plans" /><Card label="Loading plans"><AccountWait label="Loading plans" /></Card></div>;
  return (
    <div className="k-page">
      <PageHeader eyebrow="Account · Plans" title="Plans"
        lede={intro.lede}
        actions={<Link to="/account" className="btn quiet sm">← Account</Link>} />
      <PromoCountdown plansLink={false} />
      {!billing && me && (
        // the line above already says Basic and Pro aren't on sale yet: this box only offers the way to hear when they are (VR3-012)
        <Notice label="Paid plans aren't on sale yet" actions={<PlanInterestButton source="plans" />}>
          Press the button and we'll tell you the day they open.
        </Notice>
      )}
      {billing && yearlyOk && (
        <FormGrid label="Price options">
          <FieldGroup label="Billed">
            <Seg label="Billing period" value={yearly ? "year" : "month"} onChange={(v) => setYearly(v === "year")}
              options={[{ value: "month", label: "Monthly" }, { value: "year", label: YEARLY_LABEL }]} />
          </FieldGroup>
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
                {price.about && <span className="k-note" data-testid={`about-${p}`}>{price.about}</span>}
                {price.inr && gst && <span className="k-note">incl. GST</span>}
                {period === "year" && p !== "free" && savingOf(p) && <span className="k-note">Saves {savingOf(p)} a year against paying monthly</span>}
              </div>
              {/* VR6-013: about 400 characters of each card's lines, the rest one tap away (lib/plans.ts splitFeatures): the three cards stood 984, 1,176 and
                  1,015px tall, each a wall of small text that the Side by side tables below say again; every line is still in the page */}
              {(() => {
                const line = (f: string) => f.endsWith(":") ? <li key={f} className="head">{f}</li> : <li key={f}><span aria-hidden="true">✓</span>{f}</li>;
                const { head, shown, more } = splitFeatures(FEATURES[p]);
                return (
                  <>
                    <ul className="k-plan-list">{[...head, ...shown].map(line)}</ul>
                    {more.length > 0 && (
                      <details className="k-plan-more" data-testid={`plan-more-${p}`}>
                        <summary>{more.length} more included in {planName(p)}</summary>
                        <ul className="k-plan-list">{more.map(line)}</ul>
                      </details>
                    )}
                  </>
                );
              })()}
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
      <PlanCompare folded plans={me?.plans as Record<string, Partial<Limits>> | undefined} />
      {me && paid !== "free" && me.billing.renews_or_ends && (
        <p className="k-small k-muted">{me.billing.cancel_at_period_end ? "Ends" : "Renews"} on {dateOnly(me.billing.renews_or_ends)}.</p>
      )}
      {billing ? (
        <p className="k-small k-muted k-measure">{gst ? "Rupee prices include 18% GST, and every payment gets a GST invoice in Account." : "The price shown is all you pay: no GST is added. Every payment gets an invoice in Account."} Paid plans renew automatically each month or year until you cancel, which you can do any time from Account. By subscribing you agree to the <Link className="link" to="/terms">terms</Link> and the <Link className="link" to="/refunds">cancellation and refund policy</Link>. Payments are handled securely by our payment partner.</p>
      ) : (
        <p className="k-small k-muted k-measure">{finePrint(offer, { currency: "INR", inRupees: false, inRupeesYear: false,
          charged: { basic: `₹${rupees("basic", "month").toLocaleString("en-IN")}`, pro: `₹${rupees("pro", "month").toLocaleString("en-IN")}` }, gst }).join(" ")}</p>
      )}
      <p className="k-small k-muted k-measure" data-testid="usd-note">{usdNote(rate, pricing?.usd_inr?.fallback)}</p>
      <p className="k-small k-muted k-measure">StratLab is a research and paper trading tool. It doesn't place real orders or give investment advice, and past results don't predict future returns.</p>
      <LegalLinks blog />
      {switching && (
        <ConfirmDialog title={paid !== "free" && me ? `Switch to ${planName(switching)}?` : `Subscribe to ${planName(switching)}?`}
          confirmLabel={`Continue to payment · ${chargeAmount(switching)}`} danger={false}
          onClose={() => setSwitching(null)} onConfirm={() => { const p = switching; setSwitching(null); void subscribe(p); }}>
          <span data-testid="plan-confirm">
            {planName(switching)} plan, billed {period === "year" ? "yearly" : "monthly"}: {chargeWords(switching)}. It renews automatically
            each {period} until you cancel, any time from Account. {paymentWindowLine(planName(switching), period)}
            {paid !== "free" && me && !given ? ` ${switchEndsNote(planName(paid as PlanId))}` : ""}
          </span>
        </ConfirmDialog>
      )}
    </div>
  );
}
