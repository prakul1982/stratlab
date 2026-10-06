import { useState } from "react";
import { Link } from "react-router-dom";
import { api, supabase } from "../lib/api";
import { useApp } from "../lib/app";
import { dateOnly } from "../lib/format";
import { HELP } from "../lib/help";
import { LegalLinks } from "../components/LegalLinks";
import { InvoicesCard } from "../components/InvoicesCard";
import { Badge, Card, CardHead, ConfirmDialog, LinkCard, PageHeader, Skeleton } from "../components/kit";

/** How the person signed in, as the app knows it: the provider on the session. */
const PROVIDERS: Record<string, string> = { google: "Google", email: "Email link", github: "GitHub", apple: "Apple" };

/** Where each kind of saved data can be deleted. There is no single export or delete-everything call, so each one links to
 * the page that has its own delete button. */
const DATA: { to: string; title: string; what: string }[] = [
  { to: "/holdings", title: "My Holdings", what: "Your shares and ETFs. Delete them on that page." },
  { to: "/tax-report", title: "Tax report", what: "Your uploaded tradebooks. Delete them on that page." },
  { to: "/money/mutual-funds", title: "Mutual funds", what: "Your statement and its schemes. Delete them on that page." },
  { to: "/money/net-worth", title: "Net worth", what: "What you own and owe. Delete it on that page." },
  { to: "/notebooks", title: "Notebooks and experiments", what: "Your strategies and their results. Delete a notebook from its own page." },
  { to: "/alerts", title: "Stock alerts", what: "Each alert has its own Delete button." },
];

export function AccountPage() {
  const { me, session, fail, notify, refreshMe } = useApp();
  const [ask, setAsk] = useState<"cancel" | "everywhere" | null>(null);
  const [busy, setBusy] = useState(false);
  if (!me) return <div className="k-page"><PageHeader eyebrow="Account" title="Account" /><Card label="Loading your account"><Skeleton label="Loading your account" /></Card></div>;
  const b = me.billing, u = me.usage;
  const paid = me.paid_plan ?? me.plan;   // what they pay for; me.plan is Pro for everyone during the launch offer
  const meta = session?.user.user_metadata as { full_name?: string; name?: string } | undefined;
  const name = meta?.full_name || meta?.name || "";
  const provider = session?.user.app_metadata?.provider as string | undefined;
  const until = b.renews_or_ends ? ` (${dateOnly(b.renews_or_ends)})` : "";

  const cancel = async () => {
    setBusy(true);
    try { await api("/billing/cancel", { method: "POST" }); await refreshMe(); setAsk(null); notify(`Cancelled. Your plan stays until the end of the paid period${until}.`); } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const everywhere = async () => {
    setBusy(true);
    try { await supabase.auth.signOut({ scope: "global" }); } catch (e) { fail(e); setBusy(false); }
  };

  const usage: [string, string][] = [
    ...(me.promo ? [["Launch offer", `Every Pro feature free until ${dateOnly(me.promo.until)}`] as [string, string]] : []),
    ...(!me.promo && me.free_basic_until ? [["Free Basic from invites", `Until ${dateOnly(me.free_basic_until)}`] as [string, string]] : []),
    ...(paid !== "free" ? [[b.cancel_at_period_end ? "Ends on" : "Renews on", dateOnly(b.renews_or_ends)] as [string, string]] : []),
    ["Experiments this month", u.backtests_limit == null ? `${u.backtests_used} (unlimited)` : `${u.backtests_used} of ${u.backtests_limit}`],
    ["AI builds this month", u.ai_limit == null ? `${u.ai_used} (unlimited)` : `${u.ai_used} of ${u.ai_limit}`],
    ...(u.deepdive_used != null ? [["Companies in the deep dive this month", u.deepdive_limit == null ? `${u.deepdive_used} (unlimited)` : `${u.deepdive_used} of ${u.deepdive_limit}`] as [string, string]] : []),
    ...(u.deck_used != null ? [["Company decks this month", u.deck_limit == null ? `${u.deck_used} (unlimited)` : `${u.deck_used} of ${u.deck_limit}`] as [string, string]] : []),
    ["Paper sessions running", `${me.live_running} of ${me.live_limit}`],
  ];

  return (
    <div className="k-page">
      <PageHeader eyebrow="Account" title="Account" lede="Who you are, your plan and invoices, how you sign in, and where your data lives. Alerts, emails and what you see first are in Settings."
        actions={<Link to="/settings" className="btn outline sm">Settings</Link>} />

      <Card id="profile" label="Profile">
        <CardHead title="Profile" />
        <dl className="k-dl">
          {name && <div><dt>Name</dt><dd>{name}</dd></div>}
          <div><dt>Email</dt><dd>{me.email ?? session?.user.email ?? "–"}</dd></div>
          <div><dt>Signed in with</dt><dd>{provider ? PROVIDERS[provider] ?? provider : "–"}</dd></div>
          <div><dt>Plan</dt><dd>{me.plan_info.name}</dd></div>
        </dl>
      </Card>

      <Card id="plan" label="Plan and usage">
        <CardHead title="Plan and usage" info={HELP.experimentsQuota}
          actions={<Badge tone="plain" dot={false}>{me.plan_info.name}{me.promo ? " (launch offer)" : me.free_basic_until ? " (free from invites)" : ""}</Badge>} />
        <div className="k-rows">{usage.map(([k, v]) => <div key={k}><span>{k}</span><b>{v}</b></div>)}</div>
        <div className="k-row">
          {paid === "free" ? <Link to="/plans" className="btn">See paid plans</Link>
            : b.cancel_at_period_end ? <><span className="k-small k-muted">Cancelled. You keep {me.plan_info.name} until {dateOnly(b.renews_or_ends)}.</span><Link to="/plans" className="btn outline">Compare plans</Link></>
              : <><Link to="/plans" className="btn outline">Change plan</Link><button type="button" className="btn quiet danger" onClick={() => setAsk("cancel")}>Cancel subscription</button></>}
        </div>
      </Card>

      <InvoicesCard />

      <Card id="security" label="Sign-in and security">
        <CardHead title="Sign-in and security" />
        <p className="k-small k-muted k-hint-line">
          {provider === "google" ? "You sign in with your Google account, so your password and two-step settings are managed there. " : ""}
          StratLab keeps you signed in on each device until you sign out.
        </p>
        <div className="k-row">
          <button type="button" className="btn outline" onClick={() => void supabase.auth.signOut()}>Sign out</button>
          <button type="button" className="btn quiet" onClick={() => setAsk("everywhere")}>Sign out everywhere</button>
        </div>
      </Card>

      <Card id="data" label="Your data">
        <CardHead title="Your data" info="StratLab doesn't have one button that downloads or deletes everything yet. Each kind of data has its own page with its own delete button." />
        <p className="k-small k-muted k-hint-line">What you have saved stays with your account and is never shared. Each kind can be deleted on its own page.</p>
        <div className="k-linkcards">{DATA.map((d) => <LinkCard key={d.to} to={d.to} title={d.title}>{d.what}</LinkCard>)}</div>
        <p className="k-small k-muted k-hint-line">For anything else, write to us from <Link className="link" to="/contact">Contact us</Link>.</p>
      </Card>

      <LegalLinks />

      {ask === "cancel" && <ConfirmDialog title="Cancel your subscription?" confirmLabel="Cancel subscription" busy={busy} onConfirm={() => void cancel()} onClose={() => setAsk(null)}>
        You keep your plan until the end of the period you've paid for{until}, and you won't be charged again.</ConfirmDialog>}
      {ask === "everywhere" && <ConfirmDialog title="Sign out on every device?" confirmLabel="Sign out everywhere" busy={busy} onConfirm={() => void everywhere()} onClose={() => setAsk(null)}>
        You'll be signed out here and on every other phone or computer where you're signed in. Sign in again to carry on.</ConfirmDialog>}
    </div>
  );
}
