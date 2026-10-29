import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { analyticsDashboard } from "../../lib/analytics";
import { money, safeHref } from "../../lib/format";
import { Badge, Card, CardHead, Disclosure, EmptyState, ErrorState, FigureTable, HealthGrid, HealthTile, Skeleton } from "../../components/kit";
import { ViewAsCard } from "../../components/ViewAs";
import { useAdmin } from "./AdminContext";
import { attention, errorCounts, lights, paidUsers, quotaLine, revenueText } from "./attention";

type InvoiceRow = { date: string; total: number; currency: string };

const istDay = (d: Date) => d.toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

/** Admin → Overview: what needs you, a light for every service and data feed, and today's numbers. */
export function OverviewSection() {
  const { fail } = useApp();
  const { ov, jobs, reported, loading, reload, showTest } = useAdmin();
  const [invoices, setInvoices] = useState<InvoiceRow[] | null>(null);
  useEffect(() => {
    api<{ invoices: InvoiceRow[] }>("/admin/invoices").then((x) => setInvoices(x.invoices)).catch(fail);
  }, [fail, loading]);

  if (!ov) return <Card label="Loading status">{loading ? <Skeleton label="Loading the server's status" />
    : <ErrorState title="The server's status couldn't be read" action={{ label: "Try again", onClick: () => void reload() }} />}</Card>;
  const sv = ov.server, st = ov.stats;
  const todo = attention(ov, reported, jobs);
  const { services, feeds } = lights(ov, jobs);
  const today = istDay(new Date());
  const todays = (invoices ?? []).filter((i) => i.date === today);
  const rupees = todays.filter((i) => i.currency === "INR").reduce((a, i) => a + i.total, 0);
  const others = [...new Set(todays.filter((i) => i.currency !== "INR").map((i) => i.currency))];
  const paidStat = paidUsers(st);
  const errors = errorCounts(sv);
  const dash = analyticsDashboard();
  const quota = quotaLine(sv.admin_alerts?.quota);
  const aiOut = sv.ai.filter((a) => a.configured && (a.result === "quota" || a.quota_used)).length;
  // the feeds that need a look stay in view; the rest are one line until opened (DJ-008: twenty green tiles)
  const okFeeds = feeds.filter((l) => l.state === "ok"), lookFeeds = feeds.filter((l) => l.state !== "ok");
  const tested = st.test_accounts ? (showTest ? `${st.test_accounts} test accounts counted` : `${st.test_accounts} test accounts left out`) : "";

  return (
    <>
      {/* what needs you first, on a phone too; View as further down (DJ-006) */}
      <Card label="Needs your attention">
        <CardHead title="Needs your attention" actions={todo.length ? <Badge tone="warn">{todo.length} need{todo.length === 1 ? "s" : ""} a look</Badge> : <Badge tone="ok">All clear</Badge>} />
        {!todo.length ? (
          <EmptyState title="Nothing needs you">The broker is logged in, AI is answering, and there are no new errors or reports. Problems found by the daily check at 4:50 PM IST are emailed to you.</EmptyState>
        ) : (
          <div className="adm-todo">
            {todo.map((x, i) => (
              <div key={i}>
                <span className="adm-todo-t"><Badge tone={x.bad ? "warn" : "plain"}>{x.bad ? "Fix" : "Look"}</Badge><span className="adm-todo-body"><span title={x.full}>{x.text}</span><Link className="link" to={x.to}>Open {x.label} →</Link></span></span>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card label="Today's numbers">
        <CardHead title="Today's numbers" info={`Sign-ups and revenue are for today in India (IST). Server errors are the crashes since the server last started. Test accounts (the +sl- addresses made for reviewers) are ${showTest ? "counted, as asked in Users and growth" : "left out of every count; Users and growth can show them"}.`}
          actions={tested ? <span className="k-small k-muted">{tested}</span> : undefined} />
        <FigureTable label="Today" rows={[
          { key: "signups", label: "Sign-ups today", value: st.signups_today, note: `${st.new_7d} in the last 7 days · ${st.users} in all` },
          { key: "paid", label: paidStat.label, value: paidStat.value, note: paidStat.note },
          { key: "revenue", label: "Revenue today", value: invoices ? money(rupees, "INR") : "–",
            note: invoices ? `${todays.length} invoice${todays.length === 1 ? "" : "s"}${others.length ? ` · also in ${others.join(", ")}` : ""}` : undefined },
          // named for what it counts, which isn't today (DJ-005)
          { key: "errors", label: "Server errors (since restart)", value: errors.since, note: <Link className="link" to="/admin/system">{errors.before ? `${errors.before} kept from before it` : "see System"}</Link> },
        ]} />
      </Card>

      <Card label="Money, use and limits">
        <CardHead title="Money, use and limits" info="What StratLab itself can read: its own invoices, who used it, this month's experiments and AI builds, and the email service's daily limit. Bills it can't read (hosting, AI, payments) are linked to their own dashboards rather than guessed." />
        <FigureTable label="Money and use" rows={[
          { key: "rev30", label: "Revenue, last 30 days", value: st.revenue_30d ? revenueText(st.revenue_30d.by_currency, (v, c) => money(v, c)) : "–",
            note: st.revenue_30d ? `${st.revenue_30d.count} invoice${st.revenue_30d.count === 1 ? "" : "s"}` : "Not read" },
          { key: "active", label: "Active users, last 7 days", value: st.active_7d ?? "–", note: st.active_7d == null ? "Not read" : "signed in, or ran an experiment or AI build" },
          ...(st.plan_interest != null ? [{ key: "plans", label: "Waiting for plans", value: st.plan_interest, note: st.plan_interest === 1 ? "person asked to be told when plans open" : "people asked to be told when plans open" }] : []),
          { key: "emails", label: "Emails sent today", value: sv.admin_alerts?.quota?.sent_today ?? "–",
            note: quota?.left ?? (sv.admin_alerts?.via === "Brevo" ? "Brevo didn't say" : `Not read from ${sv.admin_alerts?.via ?? "the email service"}`) },
          // the month's two counts sit with the other counts, not alone in a full-width card (LIVE1C-005)
          { key: "exp", label: "Experiments this month", value: st.experiments_month, note: "all users" },
          { key: "ai", label: "AI builds this month", value: st.ai_month, note: `all users${st.ai_reads_month != null ? `; ${st.ai_reads_month} AI reads` : ""}` },
        ]} />
        <p className="k-small k-muted" data-testid="cost-links">
          Bills StratLab can't read: <a className="link" href="https://railway.com/dashboard" target="_blank" rel="noopener noreferrer">Railway (usage and bill)</a>
          {" · "}<a className="link" href="https://dashboard.razorpay.com/" target="_blank" rel="noopener noreferrer">Razorpay</a>
          {" · "}<a className="link" href="https://supabase.com/dashboard/projects" target="_blank" rel="noopener noreferrer">Supabase (usage)</a>
          {sv.admin_alerts?.quota?.dashboard && <>{" · "}<a className="link" href={safeHref(sv.admin_alerts.quota.dashboard)} target="_blank" rel="noopener noreferrer">Brevo plan</a></>}
          {aiOut > 0 && <>{" · "}{aiOut} AI provider{aiOut === 1 ? " is" : "s are"} out of free quota (<Link className="link" to="/admin/system">System</Link>)</>}
          {dash && <>{" · "}<a className="link" href={safeHref(dash)} target="_blank" rel="noopener noreferrer" data-testid="posthog-dashboard">Usage analytics dashboard</a></>}
        </p>
      </Card>

      <Card label="Services">
        <CardHead title="Services" info="Each light has its word: OK, Check (look when you can) or Problem (fix it). A tile opens where it is fixed." />
        <HealthGrid label="Services">
          {services.map((l) => <HealthTile key={l.key} state={l.state} label={l.label} detail={l.detail} to={l.to} />)}
        </HealthGrid>
      </Card>

      <Card label="Data feeds">
        <CardHead title="Data feeds" actions={<Link className="btn quiet sm" to="/admin/data">Data and jobs</Link>} />
        {!jobs ? <Skeleton label="Loading the data feeds" lines={2} /> : (
          <>
            <p className="k-small" data-testid="feeds-summary">{[okFeeds.length && `${okFeeds.length} OK`, lookFeeds.filter((l) => l.state === "warn").length && `${lookFeeds.filter((l) => l.state === "warn").length} Check`,
              lookFeeds.filter((l) => l.state === "bad").length && `${lookFeeds.filter((l) => l.state === "bad").length} Problem`].filter(Boolean).join(" · ")}</p>
            {lookFeeds.length > 0 && (
              <HealthGrid label="Data feeds that need a look">
                {lookFeeds.map((l) => <HealthTile key={l.key} state={l.state} label={l.label} detail={l.detail} to={l.to} />)}
              </HealthGrid>
            )}
            {okFeeds.length > 0 && (
              <Disclosure summary={`Show the ${okFeeds.length} feeds that are OK`} testId="feeds-ok">
                <HealthGrid label="Data feeds">
                  {okFeeds.map((l) => <HealthTile key={l.key} state={l.state} label={l.label} detail={l.detail} to={l.to} />)}
                </HealthGrid>
              </Disclosure>
            )}
          </>
        )}
      </Card>

      <ViewAsCard />
    </>
  );
}
