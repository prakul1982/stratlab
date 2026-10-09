import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { analyticsDashboard } from "../../lib/analytics";
import { money } from "../../lib/format";
import { Badge, Card, CardHead, EmptyState, HealthGrid, HealthTile, Skeleton, Stat, StatRow } from "../../components/kit";
import { ViewAsCard } from "../../components/ViewAs";
import { useAdmin } from "./AdminContext";
import { attention, errorCounts, lights, paidUsers } from "./attention";

type InvoiceRow = { date: string; total: number; currency: string };
type UserRow = { created_at: string | null };

const istDay = (d: Date) => d.toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

/** Admin → Overview: what needs you, a light for every service and data feed, and today's numbers. */
export function OverviewSection() {
  const { fail } = useApp();
  const { ov, jobs, reported, loading } = useAdmin();
  const [users, setUsers] = useState<UserRow[] | null>(null);
  const [invoices, setInvoices] = useState<InvoiceRow[] | null>(null);
  useEffect(() => {
    api<UserRow[]>("/admin/users?q=").then(setUsers).catch(fail);
    api<{ invoices: InvoiceRow[] }>("/admin/invoices").then((x) => setInvoices(x.invoices)).catch(fail);
  }, [fail, loading]);

  if (!ov) return <Card label="Loading status"><Skeleton label="Loading the server's status" /></Card>;
  const sv = ov.server, st = ov.stats;
  const todo = attention(ov, reported, jobs);
  const { services, feeds } = lights(ov, jobs);
  const today = istDay(new Date());
  const signups = users?.filter((u) => u.created_at && istDay(new Date(u.created_at)) === today).length;
  const todays = (invoices ?? []).filter((i) => i.date === today);
  const rupees = todays.filter((i) => i.currency === "INR").reduce((a, i) => a + i.total, 0);
  const others = [...new Set(todays.filter((i) => i.currency !== "INR").map((i) => i.currency))];
  const paidStat = paidUsers(st);
  const errors = errorCounts(sv);
  const dash = analyticsDashboard();

  return (
    <>
      <ViewAsCard />

      <Card label="Needs your attention">
        <CardHead title="Needs your attention" actions={todo.length ? <Badge tone="warn">{todo.length} need{todo.length === 1 ? "s" : ""} a look</Badge> : <Badge tone="ok">All clear</Badge>} />
        {!todo.length ? (
          <EmptyState title="Nothing needs you">The broker is logged in, AI is answering, and there are no new errors or reports. Problems found by the daily check at 4:50 PM IST are emailed to you.</EmptyState>
        ) : (
          <div className="adm-todo">
            {todo.map((x, i) => (
              <div key={i}>
                <span className="adm-todo-t"><Badge tone={x.bad ? "warn" : "plain"}>{x.bad ? "Fix" : "Look"}</Badge><span title={x.full}>{x.text}</span></span>
                <Link className="btn quiet sm" to={x.to}>Open {x.label}</Link>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card label="Today's numbers">
        <CardHead title="Today's numbers" info="Sign-ups and revenue are for today in India (IST). Server errors are the crashes since the server last started." />
        <StatRow label="Today">
          <Stat item label="Sign-ups today" value={signups ?? "–"} note={`${st.new_7d} in the last 7 days · ${st.users} in all`} />
          <Stat item label={paidStat.label} value={paidStat.value} note={paidStat.note} />
          <Stat item label="Revenue today" value={invoices ? money(rupees, "INR") : "–"}
            note={invoices ? `${todays.length} invoice${todays.length === 1 ? "" : "s"}${others.length ? ` · also in ${others.join(", ")}` : ""}` : undefined} />
          {st.plan_interest != null && <Stat item label="Waiting for plans" value={st.plan_interest} note={st.plan_interest === 1 ? "person asked to be told when plans open" : "people asked to be told when plans open"} />}
          <Stat item label="Server errors" value={errors.since} note={<Link className="link" to="/admin/system">since the last restart{errors.before ? ` · ${errors.before} kept from before it` : ""}</Link>} />
        </StatRow>
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
          <HealthGrid label="Data feeds">
            {feeds.map((l) => <HealthTile key={l.key} state={l.state} label={l.label} detail={l.detail} to={l.to} />)}
          </HealthGrid>
        )}
      </Card>

      <Card label="This month">
        <CardHead title="This month" />
        <StatRow label="This month">
          <Stat item label="Experiments" value={st.experiments_month} note="this month, all users" />
          <Stat item label="AI builds" value={st.ai_month} note="this month, all users" />
        </StatRow>
        {dash && (
          <div className="k-row">
            <span className="k-small k-muted">Usage analytics are on: page views and the sign-up to payment funnel, by user id only.</span>
            <a className="btn outline sm" href={dash} target="_blank" rel="noopener noreferrer" data-testid="posthog-dashboard">Open the PostHog dashboard</a>
          </div>
        )}
      </Card>
    </>
  );
}
