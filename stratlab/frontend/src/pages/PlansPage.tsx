import { useEffect, useState } from "react";
import { changeDay, graceLine } from "../lib/freeChange";
import { AccountWait } from "../components/AccountWait";
import { Card, ConfirmDialog, FieldGroup, FormGrid, Notice, PageHeader, Seg } from "../components/kit";
import { Link } from "react-router-dom";
import { LegalLinks } from "../components/LegalLinks";
import { api, loadRazorpay } from "../lib/api";
import { useApp } from "../lib/app";
import { dateOnly } from "../lib/format";
import { aboutUsd, usdCheckoutOn, usdNote, usePriceCur, usePricing } from "../lib/currency";
import { cardPrice, checkoutCur, dollarText, freePrice, usdPricesNote, usdRowOf } from "../lib/priceCurrency";
import { CurrencySwitch } from "../components/CurrencySwitch";
import { PromoCountdown } from "../components/PromoCountdown";
import { PlanCompare } from "../components/PlanCompare";
import { SampleDeckLink } from "../components/SampleDeck";
import { PlanInterestButton } from "../components/PlanInterest";
import { track } from "../lib/analytics";
import { LIMITS, PRICE, WHO, type Limits, type PlanId } from "../lib/plans";
import { KEY } from "../lib/planKeys";
import { readViewAs } from "../lib/viewAs";
import { canBuy, checkoutDescription, finePrint, paymentWindowLine, pricingIntro, rupeeCharge, switchEndsNote, viewingPlansNote, YEARLY_LABEL, yearlySaving } from "../lib/offer";

const planName = (p: PlanId) => ({ free: "Free", basic: "Basic", pro: "Pro" }[p]);

export function PlansPage() {
  const { me, session, ready, fail, notify, refreshMe, viewAs: viewAsMe } = useApp();
  // "View as" from /me once it has answered, and from this device's own choice before then: the page draws the buy
  // buttons from the public prices while /me is still on its way, and they must already be off (R7M-010, again in R8)
  const viewAs = me ? viewAsMe : readViewAs();
  const [busy, setBusy] = useState<string | null>(null);
  // rupees with "about $" beside each price (item 34), or US dollars on the "Prices in" switch (owner, 16 Nov): dollars for the US
  // region until the visitor picks, and a dollar price that checkout still charges in rupees says the rupee amount beside it
  const { pricing, rate, status: pricingStatus } = usePricing();
  const pc = usePriceCur();
  const usd = usdRowOf(pricing), cur = usd ? pc.cur : "INR", usdOn = usdCheckoutOn();
  // one answer for what's on sale today (plans.offer_state): /me's, else the public one the landing page reads
  const offer = me?.offer ?? pricing?.offer ?? null;
  const billing = offer ? canBuy(offer) : me?.billing_enabled !== false;
  const yearlyOk = offer ? offer.yearly : !!me?.yearly_enabled;
  const intro = pricingIntro(offer, LIMITS.pro, "app");
  const [yearly, setYearly] = useState(false);
  const period = yearly && yearlyOk ? "year" : "month";
  const paid = me?.paid_plan ?? me?.plan;   // me.plan is Pro for everyone during the launch offer
  // LIVE10A-003: a Free account in its grace still has its earlier decks: the line under the cards says so ("1 a month until 27 Nov")
  const deckRow = me?.free_change?.rows.find((r) => r.key === "decks_per_month" && (r.before ?? 0) > 0 && r.before !== r.after);
  const deckGrace = deckRow && me?.free_change ? `${deckRow.before} a month until ${changeDay(me.free_change.on).replace(/ \d{4}$/, "")}` : null;
  // GST is spoken of only while the invoices carry it (the seller's GSTIN is set in Admin → Money): an invoice with no GSTIN
  // says the supplier isn't registered and charges none, so "incl. GST" and "a GST invoice" would contradict it (R7M-001)
  const gst = pricing?.invoice?.gst === true;
  const rupees = (p: PlanId, per: string) => {
    const sp = me?.plans?.[p];
    return sp ? (per === "year" ? sp.price_year : sp.price) : PRICE[p][per === "year" ? 1 : 0];
  };
  /** A paid card's price in the currency shown (lib/priceCurrency): the main price, the line beside it, and what the card is charged. */
  const paidPrice = (p: "basic" | "pro", per: string) =>
    cardPrice({ plan: p, period: per === "year" ? "year" : "month", cur, inr: rupees(p, per), usd, checkoutOn: usdOn, aboutUsd: (v) => aboutUsd(v, rate) });
  /** A card's price: Free is "₹0" (or "$0"), with nothing beside it. */
  const priceOf = (p: PlanId, per: string) => {
    if (p === "free") return { shown: freePrice(cur, usd), inr: false, about: null };
    const c = paidPrice(p, per);
    return { shown: c.shown, inr: c.chargedCur === "INR", about: c.about };
  };
  /** What a year saves against twelve months, in the currency shown (rupees with their dollar figure). */
  const savingOf = (p: "basic" | "pro") => {
    if (paidPrice(p, "year").usdShown && usd) { const s = yearlySaving(usd[p], usd[`${p}_year`]); return s == null ? null : dollarText(s); }
    const save = yearlySaving(rupees(p, "month"), rupees(p, "year"));
    return save == null ? null : `₹${save.toLocaleString("en-IN")} (${aboutUsd(save, rate)})`;
  };

  const subscribe = async (plan: "basic" | "pro") => {
    track("upgrade clicked", { plan, period, source: "plans" });
    setBusy(plan);
    try {
      // the rupee plan, as before, unless dollar checkout is switched on and the server has the USD plans for this period (lib/priceCurrency)
      const currency = checkoutCur(cur, usd, period, usdOn);
      const d = await api<{ subscription_id: string; key_id: string; email: string; currency: string }>("/billing/subscribe", { method: "POST", body: { plan, period, currency } });
      // the server charges another currency than the one this page confirmed (its USD plans changed meanwhile): no payment window
      // with an amount the page didn't show
      if (d.currency && d.currency !== currency) { notify("The prices changed just now. Check the amount on the plan again, then subscribe."); setBusy(null); return; }
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
  // LIVE16B-001: the plan picked on a plan card before signing in (/plans?plan=basic, kept through Google or the email code): its card is
  // marked and brought into view once the account has answered
  const picked = new URLSearchParams(location.search).get("plan");
  useEffect(() => {
    if (me && (picked === "basic" || picked === "pro")) document.querySelector(`[data-testid="plan-card-${picked}"]`)?.scrollIntoView({ block: "center" });
  }, [!!me, picked]);     // eslint-disable-line react-hooks/exhaustive-deps
  // every purchase is confirmed on this page first, with the plan, the period, the amount charged and the renewal (R6V-009)
  const ask = (plan: "basic" | "pro") => setSwitching(plan);
  const given = !!me?.billing?.given_by_owner;
  const RANK: Record<PlanId, number> = { free: 0, basic: 1, pro: 2 };
  /** What the card is charged, in words: "₹699 incl. 18% GST (about $8), every month"; with dollars shown and rupees charged,
   * "₹699 (shown as $8; charged in rupees), every month"; with dollars charged, "$8, every month". */
  const chargeWords = (p: "basic" | "pro") => {
    const c = paidPrice(p, period);
    if (c.chargedCur === "USD") return `${c.charged}, every ${period}`;
    return `${rupeeCharge(rupees(p, period), gst)} (${c.usdShown ? `shown as ${c.shown}; charged in rupees` : aboutUsd(rupees(p, period), rate)}), every ${period}`;
  };

  /** The amount charged, alone, for the dialog's button (LIVE1B-079: "Continue to payment" did not say what it would charge). */
  const chargeAmount = (p: "basic" | "pro") => { const c = paidPrice(p, period); return c.chargedCur === "USD" ? c.charged : rupeeCharge(rupees(p, period), gst); };

  /** A card's one button. A plan you have, or one a higher plan you have includes, says so on a quiet button that can't be pressed;
   * the others buy it. */
  const action = (p: PlanId, cur: boolean) => {
    const has = paid && RANK[p] <= RANK[paid as PlanId];
    if (cur) return <button className="btn outline k-plan-btn" disabled>Current plan</button>;
    // the current plan isn't known until /me answers: no "Upgrade to Pro" for a Pro reader meanwhile
    if (!me) return <button className="btn outline k-plan-btn" disabled>Checking your plan…</button>;
    // Free is in every plan; a plan the owner gave already includes everything below it: nothing to buy there (R6V-009)
    if (p === "free" || (given && has)) return <button className="btn outline k-plan-btn" disabled data-testid="plan-included">Included in your {planName((paid ?? "free") as PlanId)} plan</button>;
    if (!billing) return <button className="btn outline k-plan-btn" disabled>Opens soon</button>;
    return (
      <button className={`btn k-plan-btn ${p === "pro" ? "" : "outline"}`} disabled={!!busy || !!viewAs} onClick={() => ask(p as "basic" | "pro")}
        title={viewAs ? viewingPlansNote(planName(viewAs)) : undefined} aria-describedby={viewAs ? "plans-viewas" : undefined}>
        {busy === p ? "Opening checkout…" : paid === "pro" && p === "basic" ? "Switch to Basic" : `Upgrade to ${planName(p)}`}
        {viewAs && <span className="k-small"> (off while viewing as {planName(viewAs)})</span>}</button>
    );
  };

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
      {/* LIVE15B-012 / LIVE16B: the "Prices in" switch holds its place while the public prices are on their way, so the plan cards under it
          never move down when they come (phone CLS 0.045-0.050) */}
      {((billing && yearlyOk) || usd || pricingStatus === "loading") && (
        <FormGrid label="Price options">
          {billing && yearlyOk && <FieldGroup label="Billed">
            <Seg label="Billing period" value={yearly ? "year" : "month"} onChange={(v) => setYearly(v === "year")}
              options={[{ value: "month", label: "Monthly" }, { value: "year", label: YEARLY_LABEL }]} />
          </FieldGroup>}
          {(usd || pricingStatus === "loading") && <FieldGroup label="Prices in"><CurrencySwitch cur={cur} auto={pc.auto} onChange={pc.choose} /></FieldGroup>}
        </FormGrid>
      )}
      {viewAs && billing && <div id="plans-viewas" data-testid="plans-viewas"><Notice tone="warn" role="status">{viewingPlansNote(planName(viewAs))}</Notice></div>}
      <div className="k-plans">
        {(["free", "basic", "pro"] as const).map((p) => {
          const cur = paid === p;
          const price = priceOf(p, period);
          return (
            <Card key={p} className={`k-plan${p === "pro" ? " pro" : ""}${picked === p ? " picked" : ""}`} testId={`plan-card-${p}`}>
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
              {/* R11 (owner, 5 Nov: "bad UI"): five short lines, the plan's main points, and one button at the foot; the cards are level (styles.css
                  .k-plans), and every limit and feature is in the comparison table under them, so nothing is folded inside a card */}
              <div className="k-plan-body">
                <ul className="k-plan-list">{KEY[p].map((f) => <li key={f}><span aria-hidden="true">✓</span>{f}</li>)}</ul>
                {p === "free" && cur && me?.free_change && <p className="k-note" data-testid="plan-grace">{graceLine(me.free_change)} <Link className="link" to="/account#free-change">See what changes</Link></p>}
                {picked === p && p !== "free" && !cur && <p className="k-note" data-testid="plan-picked">The plan you picked before signing in.</p>}
                {action(p, cur)}
              </div>
            </Card>
          );
        })}
      </div>
      {/* FREE-TIER: Free has no slide decks of its own: one real theme deck to download, so a Free reader or a visitor sees what one holds */}
      <p className="k-small k-muted" data-testid="sample-deck-line">Slide decks are on Basic and Pro{deckGrace ? ` (your Free account keeps ${deckGrace})` : ""}. <SampleDeckLink label="Download a sample deck" /></p>
      {me && paid !== "free" && me.billing.renews_or_ends && (
        <p className="k-small k-muted">{me.billing.cancel_at_period_end ? "Ends" : "Renews"} on {dateOnly(me.billing.renews_or_ends)}.</p>
      )}
      <PlanCompare plans={me?.plans as Record<string, Partial<Limits>> | undefined} grace={me?.free_change} />
      {/* the small print, short and in one place (R11, owner 5 Nov: a wall of small print under the table) */}
      <ul className="k-fineprint" aria-label="The small print">
        {billing ? (
          <>
            <li>{gst ? "Rupee prices include 18% GST, and every payment gets a GST invoice in Account." : "The price shown is all you pay: no GST is added. Every payment gets an invoice in Account."}</li>
            <li>Paid plans renew each month or year until you cancel, any time from Account. By subscribing you agree to the <Link className="link" to="/terms">terms</Link> and the <Link className="link" to="/refunds">cancellation and refund policy</Link>.</li>
          </>
        ) : finePrint(offer, { currency: "INR", inRupees: false, inRupeesYear: false,
          charged: { basic: `₹${rupees("basic", "month").toLocaleString("en-IN")}`, pro: `₹${rupees("pro", "month").toLocaleString("en-IN")}` }, gst }).map((t) => <li key={t}>{t}</li>)}
        <li data-testid="usd-note">{cur === "USD" && usd ? usdPricesNote(usd, period, usdOn) : usdNote(rate, pricing?.usd_inr?.fallback, usd)}</li>
        <li>StratLab is a research and paper trading tool: it places no real orders and gives no investment advice, and past results don't predict future returns.</li>
      </ul>
      <LegalLinks blog />
      {switching && (
        <ConfirmDialog title={paid !== "free" && me ? `Switch to ${planName(switching)}?` : `Subscribe to ${planName(switching)}?`}
          confirmLabel={`Continue to payment · ${chargeAmount(switching)}`} danger={false}
          onClose={() => setSwitching(null)} onConfirm={() => { const p = switching; setSwitching(null); void subscribe(p); }}>
          <span data-testid="plan-confirm">
            {planName(switching)} plan, billed {period === "year" ? "yearly" : "monthly"}: {chargeWords(switching)}. It renews automatically
            each {period} until you cancel, any time from Account. {paymentWindowLine(planName(switching), period, checkoutCur(cur, usd, period, usdOn))}
            {paid !== "free" && me && !given ? ` ${switchEndsNote(planName(paid as PlanId))}` : ""}
          </span>
        </ConfirmDialog>
      )}
    </div>
  );
}
