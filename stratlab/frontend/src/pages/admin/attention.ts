import type { HealthState } from "../../components/kit";
import { ago, dateOnly } from "../../lib/format";
import type { JobRow, Overview, Reported } from "./AdminContext";

export type Attention = { text: string; to: string; label: string; bad: boolean };

/** What needs a look, worst first. Each item says where it is fixed. */
export function attention(ov: Overview | null, reported: Reported | null, jobs: JobRow[] | null): Attention[] {
  if (!ov) return [];
  const sv = ov.server;
  const out: Attention[] = [];
  const aiKeys = sv.ai.filter((a) => a.configured);
  if (!sv.kite_ready) out.push({ text: sv.kite_invalid || "The broker isn't logged in today, so Indian prices and paper trading are offline.", to: "/admin/data", label: "Data and jobs", bad: true });
  if (sv.auto_login_configured && sv.auto_login.ok === false) out.push({ text: `The automatic broker login failed: ${sv.auto_login.message}`, to: "/admin/data", label: "Data and jobs", bad: true });
  const aiDown = aiKeys.filter((a) => a.last_error && !a.quota).map((a) => a.label);
  if (!aiKeys.length) out.push({ text: "No AI keys are set, so the idea builder and research reads are off.", to: "/admin/system", label: "System", bad: true });
  else if (aiDown.length) out.push({ text: `AI: ${aiDown.join(", ")} ${aiDown.length > 1 ? "aren't" : "isn't"} answering. The others take over by themselves.`, to: "/admin/system", label: "System", bad: false });
  if (sv.admin_alerts && !sv.admin_alerts.email_ready) out.push({ text: "Alert emails can't be sent yet: the server's email (SMTP) settings are missing.", to: "/admin/system", label: "System", bad: true });
  if (sv.recent_errors?.length) out.push({ text: `${sv.recent_errors.length} server error${sv.recent_errors.length > 1 ? "s" : ""} since the last restart.`, to: "/admin/system", label: "System", bad: false });
  const pending = (reported?.entries ?? []).filter((r) => r.hidden_by !== "admin").length;
  if (pending) out.push({ text: `${pending} library entr${pending > 1 ? "ies were" : "y was"} reported by users.`, to: "/admin/quality", label: "Quality", bad: false });
  for (const j of jobs ?? []) if (j.state === "bad") out.push({ text: `${j.name}: ${j.error}`, to: "/admin/data", label: "Data and jobs", bad: false });
  if (sv.calendar?.days_left != null && sv.calendar.days_left < 60) out.push({ text: `Exchange holidays are only known for ${sv.calendar.days_left} more days.`, to: "/admin/data", label: "Data and jobs", bad: false });
  if (!sv.billing_enabled) out.push({ text: "Payments aren't connected, so paid plans show \"Coming soon\".", to: "/admin/money", label: "Money", bad: false });
  return out.sort((x, y) => Number(y.bad) - Number(x.bad));
}

export type Light = { key: string; label: string; state: HealthState; detail: string; to?: string };

const jobDetail = (j: JobRow): string => j.error ? j.error : j.last_run ? `last run ${ago(j.last_run)}` : j.schedule === "Off" ? "Off" : "not run yet";

/** A light for every service and every data feed. */
export function lights(ov: Overview | null, jobs: JobRow[] | null): { services: Light[]; feeds: Light[] } {
  if (!ov) return { services: [], feeds: [] };
  const sv = ov.server;
  const services: Light[] = [];
  services.push({ key: "kite", label: "Broker data (India)", state: sv.kite_ready ? "ok" : "bad",
    detail: sv.kite_ready ? `logged in${sv.kite_token_day ? ` for ${dateOnly(sv.kite_token_day)}` : ""}` : sv.kite_invalid || "not logged in today", to: "/admin/data" });
  services.push({ key: "feed", label: "Live price feed", state: sv.feed_connected || sv.live_sessions === 0 ? "ok" : "warn",
    detail: sv.feed_connected ? "connected" : sv.live_sessions ? "not connected" : "idle, no India sessions running", to: "/admin/data" });
  services.push({ key: "auto", label: "Automatic daily login", state: !sv.auto_login_configured ? "warn" : sv.auto_login.ok === false ? "bad" : sv.auto_login.ok ? "ok" : "warn",
    detail: !sv.auto_login_configured ? "off" : `${sv.auto_login.message}${sv.auto_login.at ? ` (${ago(sv.auto_login.at)})` : ""}`, to: "/admin/data" });
  const keys = sv.ai.filter((a) => a.configured);
  const up = keys.filter((a) => !a.last_error || a.quota).length;
  services.push({ key: "ai", label: "AI providers", state: !keys.length ? "bad" : up === keys.length ? "ok" : up ? "warn" : "bad",
    detail: keys.length ? `${up} of ${keys.length} answering` : "no keys set", to: "/admin/system" });
  if (sv.admin_alerts) services.push({ key: "mail", label: "Alert emails", state: sv.admin_alerts.email_ready ? "ok" : "bad", detail: sv.admin_alerts.email_ready ? "ready" : "email settings missing", to: "/admin/system" });
  services.push({ key: "co", label: "US company data", state: sv.research?.finnhub ? "ok" : "warn", detail: sv.research?.finnhub ? "key is set" : "no key", to: "/admin/system" });
  services.push({ key: "pay", label: "Payments", state: sv.billing_enabled ? "ok" : "warn", detail: sv.billing_enabled ? "connected" : "not set up", to: "/admin/money" });
  if (sv.calendar?.days_left != null) services.push({ key: "cal", label: "Exchange holidays", state: sv.calendar.days_left < 30 ? "bad" : sv.calendar.days_left < 60 ? "warn" : "ok",
    detail: `known for ${sv.calendar.days_left} more days`, to: "/admin/data" });
  const feeds: Light[] = (jobs ?? []).map((j) => ({ key: j.id, label: j.name, state: j.state, detail: jobDetail(j), to: "/admin/data" }));
  return { services, feeds };
}

export { jobDetail };
