import { useState } from "react";
import { Link } from "react-router-dom";
import { api, supabase } from "../lib/api";
import { useApp } from "../lib/app";
import { download } from "../lib/share";
import { dateOnly } from "../lib/format";
import { HELP } from "../lib/help";
import { LegalLinks } from "../components/LegalLinks";
import { InvoicesCard } from "../components/InvoicesCard";
import { Badge, Card, CardHead, ConfirmDialog, Field, FormActions, FormGrid, LinkCard, PageHeader, Skeleton } from "../components/kit";
import { Modal } from "../components/ui";
import { confirmMatches, monthlyUse, planRow, planRun, signedInWith } from "../lib/account";

const PLAN_NAME: Record<string, string> = { free: "Free", basic: "Basic", pro: "Pro" };


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
  const [ask, setAsk] = useState<"cancel" | "everywhere" | "erase" | null>(null);
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  if (!me) return <div className="k-page"><PageHeader eyebrow="Account" title="Account" /><Card label="Loading your account"><Skeleton label="Loading your account" /></Card></div>;
  const b = me.billing, u = me.usage;
  const meta = session?.user.user_metadata as { full_name?: string; name?: string } | undefined;
  const name = meta?.full_name || meta?.name || "";
  const provider = (session?.user.app_metadata?.provider as string | undefined) || me.signed_in_with || undefined;
  const method = signedInWith(provider, null);
  const run = planRun(me), row = planRow(me);   // the plan they have, not the launch offer (me.plan is Pro for everyone then)
  const until = b.renews_or_ends ? ` (${dateOnly(b.renews_or_ends)})` : "";
  const planName = PLAN_NAME[me.paid_plan ?? me.plan] ?? me.plan_info.name;

  const cancel = async () => {
    setBusy(true);
    try { await api("/billing/cancel", { method: "POST" }); await refreshMe(); setAsk(null); notify(`Cancelled. Your plan stays until the end of the paid period${until}.`); } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const exportAll = async () => {
    setExporting(true);
    try {
      const r = await api<Response>("/me/export", { raw: true });
      download(await r.blob(), "stratlab-my-data.json");
      notify("Your data is downloaded: stratlab-my-data.json.");
    } catch (e) { fail(e); } finally { setExporting(false); }
  };
  const everywhere = async () => {
    setBusy(true);
    try { await supabase.auth.signOut({ scope: "global" }); } catch (e) { fail(e); setBusy(false); }
  };

  const usage: [string, string][] = [
    ...(me.promo ? [["Launch offer", `Every Pro feature free until ${dateOnly(me.promo.until)}`] as [string, string]] : []),
    ...(!me.promo && me.free_basic_until ? [["Free Basic from invites", `Until ${dateOnly(me.free_basic_until)}`] as [string, string]] : []),
    ...(row ? [row] : []),
    ["Backtests this month", monthlyUse(u.backtests_used, u.backtests_limit)],
    ["AI builds this month", monthlyUse(u.ai_used, u.ai_limit)],
    // the plan's own limits are the Plans page's; when early access or the launch offer lifts them, it says so
    ...(u.deepdive_used != null ? [["Deep dives this month", monthlyUse(u.deepdive_used, u.deepdive_limit, u.deepdive_plan_limit, u.lifted_by, planName)] as [string, string]] : []),
    ...(u.deck_used != null ? [["Slide decks this month", monthlyUse(u.deck_used, u.deck_limit, u.deck_plan_limit, u.lifted_by, planName)] as [string, string]] : []),
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
          {method && <div><dt>Signed in with</dt><dd>{method}</dd></div>}
          <div><dt>Plan</dt><dd>{me.plan_info.name}</dd></div>
        </dl>
      </Card>

      <Card id="plan" label="Plan and usage">
        <CardHead title="Plan and usage" info={HELP.experimentsQuota}
          actions={<Badge tone="plain" dot={false}>{me.plan_info.name}{me.promo ? " (launch offer)" : me.free_basic_until ? " (free from invites)" : ""}</Badge>} />
        <div className="k-rows">{usage.map(([k, v]) => <div key={k}><span>{k}</span><b>{v}</b></div>)}</div>
        <div className="k-row">
          {run === "free" ? <Link to="/plans" className="btn">See paid plans</Link>
            : run === "given" ? <Link to="/plans" className="btn outline">Compare plans</Link>
            : run === "cancelled" ? <><span className="k-small k-muted">Cancelled. You keep {me.plan_info.name} until {dateOnly(b.renews_or_ends)}.</span><Link to="/plans" className="btn outline">Compare plans</Link></>
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
        <CardHead title="Your data" info="StratLab doesn't have a download of everything yet. Each kind of data can be deleted on its own page, or all of it at once below." />
        <p className="k-small k-muted k-hint-line">What you have saved stays with your account and is never shared. Each kind can be deleted on its own page.</p>
        <div className="k-linkcards">{DATA.map((d) => <LinkCard key={d.to} to={d.to} title={d.title}>{d.what}</LinkCard>)}</div>
        <h3 className="k-sub">Download everything</h3>
        <p className="k-small k-muted k-hint-line">One JSON file with everything StratLab keeps for you: your profile, holdings, tradebooks and funds, net worth,
          notebooks and experiments, journal, drawings, alerts and preferences. Tokens and passwords are left out.</p>
        <div className="k-row"><button type="button" className="btn outline" disabled={exporting} onClick={() => void exportAll()}>{exporting ? "Preparing…" : "Download all my data"}</button></div>
        <h3 className="k-sub">Delete everything</h3>
        <p className="k-small k-muted k-hint-line">
          Removes everything above, plus your chart drawings, connected accounts, alerts and preferences, with no way back. Your sign-in account,
          plan and payment records stay: payment records are kept as the law asks, and closing the sign-in account itself is done by us on request,
          through Contact us at the bottom of this page.
        </p>
        <div className="k-row"><button type="button" className="btn quiet danger" onClick={() => setAsk("erase")}>Delete all my data…</button></div>
      </Card>

      <LegalLinks />

      {ask === "cancel" && <ConfirmDialog title="Cancel your subscription?" confirmLabel="Cancel subscription" busy={busy} onConfirm={() => void cancel()} onClose={() => setAsk(null)}>
        You keep your plan until the end of the period you've paid for{until}, and you won't be charged again.</ConfirmDialog>}
      {ask === "everywhere" && <ConfirmDialog title="Sign out on every device?" confirmLabel="Sign out everywhere" busy={busy} onConfirm={() => void everywhere()} onClose={() => setAsk(null)}>
        You'll be signed out here and on every other phone or computer where you're signed in. Sign in again to carry on.</ConfirmDialog>}
      {ask === "erase" && <DeleteMyData email={me.email ?? session?.user.email ?? ""} onClose={() => setAsk(null)} />}
    </div>
  );
}

/** Deleting all your own data, in the page: the account's email typed in first (never the browser's own box). */
function DeleteMyData({ email, onClose }: { email: string; onClose: () => void }) {
  const { notify, fail, refreshMe } = useApp();
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const ok = confirmMatches(typed, email);
  const erase = async () => {
    if (!ok) return;
    setBusy(true);
    try {
      const r = await api<{ ok: boolean; failed: { label: string }[] }>("/me/delete-data", { method: "POST", body: { confirm: typed } });
      notify(r.ok ? "Your data is deleted. Your sign-in account and plan stay." : `Deleted, except: ${r.failed.map((f) => f.label).join(", ")}. Try again to finish.`);
      await refreshMe();
      onClose();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  return (
    <Modal title="Delete all your data?" onClose={onClose}>
      <div className="k-stack">
        <p className="k-small k-muted">Your holdings, tradebooks, funds, net worth, notebooks and experiments, chart drawings, connected accounts, alerts and
          preferences are removed, with no way back. Your sign-in account, plan and payment records stay.</p>
        <FormGrid label="Delete all my data" onSubmit={(e) => { e.preventDefault(); void erase(); }}>
          <Field label="Type your email to confirm" wide value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={email} autoComplete="off" spellCheck={false} />
          <FormActions>
            <button type="submit" className="btn danger" disabled={!ok || busy}>{busy ? "Deleting…" : "Delete all my data"}</button>
            <button type="button" className="btn quiet" onClick={onClose}>Cancel</button>
          </FormActions>
        </FormGrid>
      </div>
    </Modal>
  );
}
