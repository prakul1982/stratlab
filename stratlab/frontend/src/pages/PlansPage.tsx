import { useState } from "react";
import { Link } from "react-router-dom";
import { LegalLinks } from "../components/LegalLinks";
import { api, loadRazorpay } from "../lib/api";
import { useApp } from "../lib/app";
import { dateOnly } from "../lib/format";
import { money, usePricing } from "../lib/currency";
import { PromoCountdown } from "../components/PromoCountdown";
import { track } from "../lib/analytics";
import { EVERYONE, FEATURES, FLAGS, LIMITS, NUMBERS, PRICE, WHO, type Limits, type PlanId } from "../lib/plans";

/** Every limit and feature side by side, from the server's plans when signed in. */
function Compare({ plans }: { plans?: Record<string, Partial<Limits>> }) {
  const lim = (p: PlanId): Limits => ({ ...LIMITS[p], ...(plans?.[p] ?? {}) });
  const num = (p: PlanId, k: keyof Limits) => {
    const v = lim(p)[k] as number | null;
    return v == null ? "Unlimited" : p === "free" && k === "live_limit" ? `${v}, for 5 market days` : v.toLocaleString("en-IN");
  };
  const ids: PlanId[] = ["free", "basic", "pro"];
  return (
    <section className="card stack" style={{ gap: 12 }} aria-labelledby="compare-h">
      <h2 className="h2" id="compare-h">Side by side</h2>
      <div className="table-wrap"><table className="plan-compare">
        <thead><tr><th>Backtests, research and paper trading</th>{ids.map((p) => <th key={p}>{{ free: "Free", basic: "Basic", pro: "Pro" }[p]}</th>)}</tr></thead>
        <tbody>
          {NUMBERS.map(([k, label]) => <tr key={k}><td>{label}</td>{ids.map((p) => <td key={p}>{num(p, k)}</td>)}</tr>)}
          {FLAGS.map(([f, label]) => <tr key={f}><td>{label}</td>{ids.map((p) => <td key={p} aria-label={lim(p).features.includes(f) ? "Included" : "Not included"}>{lim(p).features.includes(f) ? "✓" : "–"}</td>)}</tr>)}
          {EVERYONE.map((label) => <tr key={label}><td>{label}</td>{ids.map((p) => <td key={p} aria-label="Included">✓</td>)}</tr>)}
        </tbody>
      </table></div>
    </section>
  );
}

export function PlansPage() {
  const { me, fail, notify, refreshMe } = useApp();
  const [busy, setBusy] = useState<string | null>(null);
  const billing = me?.billing_enabled !== false;
  const yearlyOk = !!me?.yearly_enabled;
  const [yearly, setYearly] = useState(false);
  const period = yearly && yearlyOk ? "year" : "month";
  const paid = me?.paid_plan ?? me?.plan;   // me.plan is Pro for everyone during the launch offer
  const { pricing, currency, pick } = usePricing();
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
    return { shown: money(row, local, currency), charged: chargedIn === "INR" ? money(inr, rupees(p, per), "INR") : null, inr: false };
  };
  const anyRupees = currency !== "INR" && !!row && (period === "year" ? row.yearly_charged_in : row.charged_in) === "INR";

  const subscribe = async (plan: "basic" | "pro") => {
    if (me && paid !== "free" && !confirm(`Switch to ${plan === "pro" ? "Pro" : "Basic"}? Your current subscription stops billing once the new one is active.`)) return;
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

  return (
    <div className="stack" style={{ gap: 26 }}>
      <div className="stack" style={{ gap: 8 }}>
        <Link to="/account" className="link small" style={{ alignSelf: "flex-start" }}>← Account</Link>
        <h1 className="page-title">Plans</h1>
        <PromoCountdown plansLink={false} />
        <p className="muted" style={{ fontSize: 17 }}>
          {billing ? "Billed through Razorpay. Cancel any time; your plan stays active until the paid period ends." : "Paid plans are coming soon. During early access every feature is unlocked for everyone; the Free plan's monthly limits still apply."}
        </p>
        {pricing && (
          <label className="row small" style={{ gap: 10, alignSelf: "flex-start" }}>Prices in
            <span className="chip-select"><select value={currency} onChange={(e) => pick(e.target.value)} aria-label="Currency">
              {Object.entries(pricing.currencies).map(([c, r]) => <option key={c} value={c}>{c} · {r.name}</option>)}
            </select></span>
          </label>
        )}
        {anyRupees && billing && <p className="small muted" style={{ margin: 0, maxWidth: "80ch" }}>Paid in rupees for now: your card is charged the rupee price shown under each plan and your bank converts it, so the amount in {currency} can differ slightly.</p>}
        {billing && yearlyOk && (
          <div className="seg" role="group" aria-label="Billing period" style={{ alignSelf: "flex-start" }}>
            <button className={!yearly ? "on" : ""} aria-pressed={!yearly} onClick={() => setYearly(false)}>Monthly</button>
            <button className={yearly ? "on" : ""} aria-pressed={yearly} onClick={() => setYearly(true)}>Yearly · 2 months free</button>
          </div>
        )}
      </div>
      <div className="grid4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
        {(["free", "basic", "pro"] as const).map((p) => {
          const cur = paid === p;
          const price = priceOf(p, period);
          return (
            <div key={p} className="card stack" style={{ gap: 14, border: p === "pro" ? "2px solid var(--ink)" : undefined }}>
              <div className="stack" style={{ gap: 2 }}>
                <h2 className="h2">{{ free: "Free", basic: "Basic", pro: "Pro" }[p]}</h2>
                <span className="small muted">{WHO[p]}</span>
              </div>
              <div className="stack" style={{ gap: 2 }}>
                <div className="serif" style={{ fontSize: 44, letterSpacing: "-0.02em" }}>{price.shown}<span className="small muted" style={{ fontFamily: "var(--sans)" }}> / {period}</span></div>
                {price.inr && <span className="tiny muted">incl. GST</span>}
                {price.charged && <span className="tiny muted">Charged as {price.charged} incl. GST / {period}</span>}
              </div>
              <ul className="stack" style={{ gap: 8, listStyle: "none", padding: 0, margin: 0, flex: 1 }}>
                {FEATURES[p].map((f) => f.endsWith(":") ? <li key={f} className="small muted" style={{ fontWeight: 600 }}>{f}</li>
                  : <li key={f} className="row" style={{ alignItems: "flex-start", gap: 10 }}><span style={{ color: "var(--blue)", fontWeight: 700 }}>✓</span>{f}</li>)}
              </ul>
              {cur ? <button className="btn outline" disabled>Current plan</button>
                : p === "free" ? <span className="small muted">Included whenever a paid plan ends</span>
                  : !billing ? <button className="btn outline" disabled>Coming soon</button>
                    : <button className={`btn ${p === "pro" ? "" : "outline"}`} disabled={!!busy} onClick={() => subscribe(p)}>
                      {busy === p ? "Opening checkout…" : paid === "pro" && p === "basic" ? "Switch to Basic" : `Upgrade to ${p === "pro" ? "Pro" : "Basic"}`}</button>}
            </div>
          );
        })}
      </div>
      <Compare plans={me?.plans as Record<string, Partial<Limits>> | undefined} />
      {me && paid !== "free" && me.billing.renews_or_ends && (
        <p className="small muted">{me.billing.cancel_at_period_end ? "Ends" : "Renews"} on {dateOnly(me.billing.renews_or_ends)}.</p>
      )}
      <p className="small muted" style={{ maxWidth: "80ch" }}>Rupee prices include 18% GST, and every payment gets a GST invoice in Account. Paid plans renew automatically each month or year until you cancel, which you can do any time from Account. By subscribing you agree to the <Link className="link" to="/terms">terms</Link> and the <Link className="link" to="/refunds">cancellation and refund policy</Link>. Payments are handled securely by Razorpay.</p>
      <p className="small muted" style={{ maxWidth: "80ch" }}>StratLab is a research and paper trading tool. It doesn't place real orders or give investment advice, and past results don't predict future returns.</p>
      <LegalLinks />
    </div>
  );
}
