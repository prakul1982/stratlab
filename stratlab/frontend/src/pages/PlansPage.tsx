import { useState } from "react";
import { api, loadRazorpay } from "../lib/api";
import { useApp } from "../lib/app";
import { dateOnly } from "../lib/format";

const FEATURES: Record<string, string[]> = {
  free: ["5 experiments a month, each with a full verdict", "10 AI strategy builds a month", "24-hour paper trading trial",
    "Every market: India, crypto, the US, UK, Europe, Japan, forex and your own CSV", "SMA, EMA, RSI and price rules"],
  basic: ["50 experiments a month", "100 AI builds a month", "Paper trade 1 strategy at a time", "Every market, real costs and tax estimates",
    "SMA, EMA, RSI and price rules"],
  pro: ["Unlimited experiments", "Unlimited AI builds", "Paper trade 5 strategies at a time", "All 20+ indicators: MACD, Bollinger Bands, VWAP, Supertrend, ADX, Stochastic, Donchian and more",
    "Indian F&O", "Telegram and email trade alerts", "Export rules and trades"],
};
const WHO: Record<string, string> = { free: "Test a few ideas", basic: "For traders testing one idea at a time", pro: "For active traders running several strategies" };

export function PlansPage() {
  const { me, fail, notify, refreshMe } = useApp();
  const [busy, setBusy] = useState<string | null>(null);
  const billing = me?.billing_enabled !== false;

  const subscribe = async (plan: "basic" | "pro") => {
    if (me && me.plan !== "free" && !confirm(`Switch to ${plan === "pro" ? "Pro" : "Basic"}? Your current subscription stops billing once the new one is active.`)) return;
    setBusy(plan);
    try {
      const d = await api<{ subscription_id: string; key_id: string; email: string }>("/billing/subscribe", { method: "POST", body: { plan } });
      await loadRazorpay();
      const rz = new window.Razorpay({
        key: d.key_id, subscription_id: d.subscription_id, name: "StratLab",
        description: plan === "pro" ? "Pro plan, ₹4,900 / month" : "Basic plan, ₹1,999 / month",
        prefill: { email: d.email || "" }, theme: { color: "#1D1B17" },
        handler: async (resp: unknown) => {
          try { await api("/billing/verify", { method: "POST", body: resp }); await refreshMe(); notify(`You're on ${plan === "pro" ? "Pro" : "Basic"} now.`); }
          catch (e) { fail(e); }
        },
        modal: { ondismiss: () => setBusy(null) },
      });
      rz.on("payment.failed", (r: { error: { description: string } }) => notify(`Payment failed: ${r.error.description}`));
      rz.open();
    } catch (e) { fail(e); setBusy(null); }
  };

  return (
    <div className="stack" style={{ gap: 26 }}>
      <div className="stack" style={{ gap: 8 }}>
        <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em" }}>Plans</h1>
        <p className="muted" style={{ fontSize: 17 }}>
          {billing ? "Billed monthly through Razorpay. Cancel any time; your plan stays active until the paid month ends." : "Paid plans are coming soon. During early access every Pro feature (all indicators, F&O, alerts, export) is unlocked for everyone; the Free plan's monthly limits still apply."}
        </p>
      </div>
      <div className="grid4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
        {(["free", "basic", "pro"] as const).map((p) => {
          const cur = me?.plan === p;
          const price = { free: 0, basic: 1999, pro: 4900 }[p];
          return (
            <div key={p} className="card stack" style={{ gap: 14, border: p === "pro" ? "2px solid var(--ink)" : undefined }}>
              <div className="stack" style={{ gap: 2 }}>
                <h2 className="h2">{{ free: "Free", basic: "Basic", pro: "Pro" }[p]}</h2>
                <span className="small muted">{WHO[p]}</span>
              </div>
              <div className="serif" style={{ fontSize: 44, letterSpacing: "-0.02em" }}>₹{price.toLocaleString("en-IN")}<span className="small muted" style={{ fontFamily: "var(--sans)" }}> / month</span></div>
              <ul className="stack" style={{ gap: 8, listStyle: "none", padding: 0, margin: 0, flex: 1 }}>
                {FEATURES[p].map((f) => <li key={f} className="row" style={{ alignItems: "flex-start", gap: 10 }}><span style={{ color: "var(--blue)", fontWeight: 700 }}>✓</span>{f}</li>)}
              </ul>
              {cur ? <button className="btn outline" disabled>Current plan</button>
                : p === "free" ? <span className="small muted">Included whenever a paid plan ends</span>
                  : !billing ? <button className="btn outline" disabled>Coming soon</button>
                    : <button className={`btn ${p === "pro" ? "" : "outline"}`} disabled={!!busy} onClick={() => subscribe(p)}>
                      {busy === p ? "Opening checkout…" : me?.plan === "pro" && p === "basic" ? "Switch to Basic" : `Upgrade to ${p === "pro" ? "Pro" : "Basic"}`}</button>}
            </div>
          );
        })}
      </div>
      {me && me.plan !== "free" && me.billing.renews_or_ends && (
        <p className="small muted">{me.billing.cancel_at_period_end ? "Ends" : "Renews"} on {dateOnly(me.billing.renews_or_ends)}.</p>
      )}
      <p className="small muted" style={{ maxWidth: "80ch" }}>StratLab is a research and paper trading tool. It doesn't place real orders or give investment advice, and past results don't predict future returns.</p>
    </div>
  );
}
