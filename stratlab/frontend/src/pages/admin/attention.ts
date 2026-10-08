import type { HealthState } from "../../components/kit";
import { ago, dateOnly } from "../../lib/format";
import type { AIRow, JobRow, Overview, Reported } from "./AdminContext";

/* One reading of the server's status for all of Admin: Overview's lights and "Needs your attention", the rows on Data and
 * jobs and on System all come from services() below, so two pages can never tell the same fact two ways. */

export type Attention = { text: string; to: string; label: string; bad: boolean };
export type Light = { key: string; label: string; state: HealthState; detail: string; to?: string };
/** A service: its light, and `fix`, the longer words for the page where it's set up (System, Data and jobs). */
export type Service = Light & { fix?: string };

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** The India paper sessions that need the broker's live feed (other markets are polled). Older servers sent only the total. */
export const indiaSessions = (sv: Overview["server"]): number => sv.india_sessions ?? sv.live_sessions;

/** Whether a provider with a key can answer now: the server's own reading (a short rate limit or a used-up free quota
 * still counts as up; one listed model it can't use doesn't make it down). Older servers sent only the last error. */
export const aiUp = (a: AIRow): boolean => (a.answering ?? null) !== null ? !!a.answering : !a.last_error || !!a.quota;

/** Every service's light, worded once. */
export function services(ov: Overview | null): Service[] {
  if (!ov) return [];
  const sv = ov.server;
  const out: Service[] = [];
  out.push({ key: "kite", label: "Broker data (India)", state: sv.kite_ready ? "ok" : "bad", to: "/admin/data",
    detail: sv.kite_invalid ? sv.kite_invalid : sv.kite_ready ? `Logged in${sv.kite_token_day ? ` for ${dateOnly(sv.kite_token_day)}` : ""}` : "Not logged in today, so Indian prices and paper trading are offline." });
  const india = indiaSessions(sv);
  out.push({ key: "feed", label: "Live price feed", state: sv.feed_connected || india === 0 ? "ok" : "warn", to: "/admin/data",
    detail: sv.feed_connected ? `Connected${india ? `, ${plural(india, "India paper session")} running` : ""}`
      : india ? `Not connected, with ${plural(india, "India paper session")} running` : "Idle: no India paper sessions running" });
  out.push({ key: "auto", label: "Automatic daily login", to: "/admin/data",
    state: !sv.auto_login_configured ? "warn" : sv.auto_login.ok === false ? "bad" : sv.auto_login.ok ? "ok" : "warn",
    detail: !sv.auto_login_configured ? "Off" : `${sv.auto_login.message}${sv.auto_login.at ? ` (${ago(sv.auto_login.at)})` : ""}`,
    fix: !sv.auto_login_configured ? "Off. Log in by hand each morning, or set the automatic login variables (setup guide, step 2)." : undefined });
  const keys = sv.ai.filter((a) => a.configured);
  const up = keys.filter(aiUp).length;
  out.push({ key: "ai", label: "AI providers", state: !keys.length ? "bad" : up === keys.length ? "ok" : up ? "warn" : "bad", to: "/admin/system",
    detail: keys.length ? `${up} of ${keys.length} answering` : "No keys set" });
  if (sv.admin_alerts) {
    const a = sv.admin_alerts;
    out.push({ key: "mail", label: "Alert emails", state: a.email_ready ? "ok" : "bad", to: "/admin/system",
      detail: a.email_ready ? (a.via ? `Sent through ${a.via}` : "Ready") : "Not set up: no email service on the server",
      fix: a.email_ready ? `Emailed to ${a.to.join(", ")}${a.via ? ` through ${a.via}` : ""}, plus your phone or Telegram if set in Account.`
        : "No email service is set up on the server. Add one in Railway: RESEND_API_KEY (a free account at resend.com made with this address), "
          + "or BREVO_API_KEY, or SMTP_HOST, SMTP_USER and SMTP_PASSWORD. Until then alerts reach only your phone or Telegram." });
  }
  out.push({ key: "co", label: "US company data", state: sv.research?.finnhub ? "ok" : "warn", to: "/admin/system",
    detail: sv.research?.finnhub ? "Key is set" : "No key",
    fix: sv.research?.finnhub ? undefined : "No key. Add the company-data key in Railway for US company pages (setup guide, step 6). India needs no key." });
  out.push({ key: "pay", label: "Payments", state: sv.billing_enabled ? "ok" : "warn", detail: sv.billing_enabled ? "Connected" : "Not set up", to: "/admin/money" });
  if (sv.calendar?.days_left != null) out.push({ key: "cal", label: "Exchange holidays", to: "/admin/data",
    state: sv.calendar.days_left < 30 ? "bad" : sv.calendar.days_left < 60 ? "warn" : "ok", detail: `Known for ${sv.calendar.days_left} more days` });
  return out;
}

/** One service by its key, for the page that shows it as a row. */
export function service(ov: Overview | null, key: string): Service | undefined {
  return services(ov).find((s) => s.key === key);
}

/** What needs a look, worst first. Each item says where it is fixed, in the same words as the service's own light. */
export function attention(ov: Overview | null, reported: Reported | null, jobs: JobRow[] | null): Attention[] {
  if (!ov) return [];
  const sv = ov.server;
  const out: Attention[] = [];
  const s = Object.fromEntries(services(ov).map((x) => [x.key, x]));
  if (s.kite.state === "bad") out.push({ text: `Broker data (India): ${s.kite.detail}`, to: "/admin/data", label: "Data and jobs", bad: true });
  if (s.auto.state === "bad") out.push({ text: `The automatic broker login failed: ${sv.auto_login.message}`, to: "/admin/data", label: "Data and jobs", bad: true });
  if (s.feed.state !== "ok") out.push({ text: `Live price feed: ${s.feed.detail}.`, to: "/admin/data", label: "Data and jobs", bad: false });
  const aiKeys = sv.ai.filter((a) => a.configured);
  const aiDown = aiKeys.filter((a) => !aiUp(a));
  if (!aiKeys.length) out.push({ text: "No AI keys are set, so the idea builder and research reads are off.", to: "/admin/system", label: "System", bad: true });
  // one line per provider that can't answer, with the provider's own reason (status code and message), so a rejected
  // key reads differently from a fault on our side (R5O-016)
  for (const a of aiDown) out.push({ text: `AI, ${a.label}: ${a.state_text || a.last_error || "not answering"}`, to: "/admin/system", label: "System", bad: false });
  if (aiDown.length && aiDown.length === aiKeys.length) out.push({ text: "No AI provider is answering, so the idea builder and research reads are off.", to: "/admin/system", label: "System", bad: true });
  if (s.mail?.state === "bad") out.push({ text: "Alert emails can't be sent yet: no email service (Resend, Brevo or SMTP) is set up on the server.", to: "/admin/system", label: "System", bad: true });
  if (sv.recent_errors?.length) out.push({ text: `${plural(sv.recent_errors.length, "server error")} since the last restart.`, to: "/admin/system", label: "System", bad: false });
  const pending = (reported?.entries ?? []).filter((r) => r.hidden_by !== "admin").length;
  if (pending) out.push({ text: `${pending} library entr${pending > 1 ? "ies were" : "y was"} reported by users.`, to: "/admin/quality", label: "Quality", bad: false });
  for (const j of jobs ?? []) if (j.state === "bad") out.push({ text: `${j.name}: ${j.error}`, to: "/admin/data", label: "Data and jobs", bad: false });
  // feeds on "Check": never run, or only partly read (R5O-016: seven sat on "Not run yet" without a word here). A job
  // switched off on purpose isn't listed.
  const waiting = (jobs ?? []).filter((j) => j.state === "warn" && j.schedule !== "Off");
  if (waiting.length) out.push({ text: `${plural(waiting.length, "data feed")} on Check: ${waiting.map((j) => `${j.name} (${jobDetail(j).toLowerCase()})`).join(", ")}.`,
    to: "/admin/data", label: "Data and jobs", bad: false });
  if (s.cal && s.cal.state !== "ok") out.push({ text: `Exchange holidays are only known for ${sv.calendar!.days_left} more days.`, to: "/admin/data", label: "Data and jobs", bad: false });
  if (!sv.billing_enabled) out.push({ text: "Payments aren't connected, so paid plans show \"Coming soon\".", to: "/admin/money", label: "Money", bad: false });
  return out.sort((x, y) => Number(y.bad) - Number(x.bad));
}

/** Overview's paid-users figure: those paying (a subscription) apart from those on a plan the owner gave by hand, so a
 * count of paid plans never sits beside "Payments aren't connected" and ₹0 as if they paid. */
export function paidUsers(st: Overview["stats"]): { label: string; value: number; note: string } {
  if (!st.paying || !st.given) return { label: "Paid users", value: st.plans.basic + st.plans.pro, note: `${st.plans.basic} Basic · ${st.plans.pro} Pro` };
  const paying = st.paying.basic + st.paying.pro, given = st.given.basic + st.given.pro;
  return { label: "Paying users", value: paying,
    note: [paying ? `${st.paying.basic} Basic · ${st.paying.pro} Pro` : "", given ? `${given} on a plan you gave, not paying` : ""].filter(Boolean).join(" · ") || "No paid plans" };
}

/** A job's line on Overview: its problem, or when it last ran. */
const jobDetail = (j: JobRow): string => j.error ? j.error : j.last_run ? `Last run ${ago(j.last_run)}` : j.schedule === "Off" ? "Off" : "Not run yet";

/** A light for every service and every data feed. */
export function lights(ov: Overview | null, jobs: JobRow[] | null): { services: Light[]; feeds: Light[] } {
  if (!ov) return { services: [], feeds: [] };
  const feeds: Light[] = (jobs ?? []).map((j) => ({ key: j.id, label: j.name, state: j.state, detail: jobDetail(j), to: "/admin/data" }));
  return { services: services(ov).map(({ fix: _fix, ...l }) => l), feeds };
}

export { jobDetail };
