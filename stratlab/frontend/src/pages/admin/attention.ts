import type { HealthState } from "../../components/kit";
import { ago, dateOnly } from "../../lib/format";
import type { AIRow, InvoiceSeller, JobRow, Overview, Reported } from "./AdminContext";

/* One reading of the server's status for all of Admin: Overview's lights and "Needs your attention", the rows on Data and
 * jobs and on System all come from services() below, so two pages can never tell the same fact two ways. */

export type Attention = { text: string; to: string; label: string; bad: boolean; /** the whole text, when `text` was cut to one line */ full?: string };

/** A provider's own error on one line: its first sentence, cut at `max` characters, so a long message with an
 * unbreakable link in it can't push a phone's page sideways (R10O-001). The whole text stays in `full` for a tooltip. */
export function oneLine(text: string, max = 120): { text: string; full?: string } {
  const flat = String(text ?? "").replace(/\s+/g, " ").trim();
  const first = flat.match(/^.*?[.!?](?=\s|$)/)?.[0] ?? flat;
  const cut = first.length > max ? `${first.slice(0, max - 1).trimEnd()}…` : first;
  return cut === flat ? { text: flat } : { text: cut, full: flat };
}
/** A provider's error with each long link in it cut to its address ("https://vercel.com/d?to=…" for a 150-character one), whole sentences
 * kept: oneLine() keeps only the first sentence, which is right for Overview's one-line list but would drop "Fix the key, then press Test."
 * on System (R11P-007: a 150-character Vercel link in the AI lines). The whole text stays in `full` for a tooltip. */
export function shortLinks(text: string | null | undefined, max = 48): { text: string; full?: string } {
  const flat = String(text ?? "").replace(/\s+/g, " ").trim();
  const cut = flat.replace(/https?:\/\/[^\s)\]]+/g, (u) => (u.length <= max ? u : `${u.slice(0, max - 1)}…`));
  return cut === flat ? { text: flat } : { text: cut, full: flat };
}
export type Light = { key: string; label: string; state: HealthState; detail: string; to?: string };
/** A service: its light, and `fix`, the longer words for the page where it's set up (System, Data and jobs). */
export type Service = Light & { fix?: string };

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** The India paper sessions that need the broker's live feed (other markets are polled). Older servers sent only the total. */
export const indiaSessions = (sv: Overview["server"]): number => sv.india_sessions ?? sv.live_sessions;

/** The live price feed's light. India's options paper sessions run on the broker's quotes read every few seconds, not on its
 * streaming feed, and are counted as running all the same (R7T-012: "Idle: no India paper sessions running" beside a
 * running NIFTY options session). */
export function feedTile(sv: Overview["server"]): Service {
  const india = indiaSessions(sv), options = sv.options_sessions ?? 0;
  // every user's sessions: said when they are more than one person's (R8O-011: "2 options paper sessions" beside the owner's 1)
  const across = (sv.options_users ?? 0) > 1 ? ` across ${sv.options_users} users` : "";
  const opts = options ? `${plural(options, "options paper session")} running${across} on quotes read every few seconds` : "";
  const detail = sv.feed_connected ? [`Connected${india ? `, ${plural(india, "India paper session")} running` : ""}`, opts].filter(Boolean).join(" · ")
    : india ? [`Not connected, with ${plural(india, "India paper session")} running`, opts].filter(Boolean).join(" · ")
    : options ? `Not needed: ${opts}` : "Idle: no India paper sessions running";
  return { key: "feed", label: "Live price feed", state: sv.feed_connected || india === 0 ? "ok" : "warn", to: "/admin/data", detail };
}

/** Whether a provider with a key can answer now: the server's own reading (a short rate limit still counts as up; a
 * used-up free quota or a paused provider does not; one listed model it can't use doesn't make it down). Older servers
 * sent only the last error. */
export const aiUp = (a: AIRow): boolean => (a.answering ?? null) !== null ? !!a.answering : !a.last_error || !!a.quota;

/** The AI providers' light, from each provider's last real result (R7M-008: "11 of 12 answering" over providers whose free
 * credit was used up, that needed a card, returned empty replies or had never been tried): how many are working, and, said
 * plainly, how many are out of credit, failing, paused or not tried yet. */
export function aiTile(ai: AIRow[]): Service {
  const keys = ai.filter((a) => a.configured);
  const up = keys.filter(aiUp).length;
  if (!keys.some((a) => a.result !== undefined)) {
    // an older server sends no last result: what it says about answering is all there is
    const quota = keys.filter((a) => a.quota_used).length;
    const paused = keys.filter((a) => aiUp(a) && (a.paused_models ?? 0) > 0).length;
    const notes = [quota ? `${quota} out of free quota` : "", paused ? `${paused} with a model paused` : ""].filter(Boolean);
    const state: HealthState = !keys.length ? "bad" : up === 0 ? "bad" : up < keys.length || paused ? "warn" : "ok";
    return { key: "ai", label: "AI providers", state, to: "/admin/system",
      detail: keys.length ? [`${up} of ${keys.length} answering`, ...notes].join(" · ") : "No keys set" };
  }
  const count = (r: string) => keys.filter((a) => (a.result ?? "untested") === r).length;
  const working = count("working"), quota = count("quota"), failing = count("failed"), paused = count("paused"), untested = count("untested");
  const slow = keys.filter((a) => a.result === "working" && (a.paused_models ?? 0) > 0).length;
  const notes = [quota ? `${quota} out of credit` : "", failing ? `${failing} failing` : "", paused ? `${paused} paused` : "",
    untested ? `${untested} not tried yet` : "", slow ? `${slow} with a model paused` : ""].filter(Boolean);
  const state: HealthState = !keys.length ? "bad" : up === 0 ? "bad" : working < keys.length || slow ? "warn" : "ok";
  // the denominator is the providers with a key, said as System says it ("12 of 13 providers set up") when some have none (R8O-008); one denominator, not two ("12" beside "12 of 13"), R7M-008
  const someUnset = ai.length > keys.length;
  return { key: "ai", label: "AI providers", state, to: "/admin/system",
    detail: [someUnset ? `${working} working of ${keys.length} set up (${ai.length} known)` : `${working} of ${keys.length} working`, ...notes].join(" · ") };
}

/** The invoice seller details still empty, said for Overview and Money (R7M-001): until a GSTIN is set every invoice is a
 * plain one that says the supplier is not registered under GST, with the Plans page promising otherwise. */
export function invoiceWarning(s: InvoiceSeller | undefined): string | null {
  if (!s || s.complete) return null;
  const all = s.missing.length >= 4;
  return `${all ? "The invoice seller details are empty" : `The invoice seller details are missing the ${s.missing.join(", ")}`}. `
    + (s.gst ? "Invoices carry GST, but are incomplete without them."
      : "Until the GSTIN is set, every invoice is a plain one that says the supplier isn't registered under GST and charges none, and the Plans page says nothing about GST. If you are registered, fill the details in before the first payment.");
}

/** Every service's light, worded once. */
export function services(ov: Overview | null, jobs: JobRow[] | null = null): Service[] {
  if (!ov) return [];
  const sv = ov.server;
  const out: Service[] = [];
  out.push({ key: "kite", label: "Broker data (India)", state: sv.kite_ready ? "ok" : "bad", to: "/admin/data",
    detail: sv.kite_invalid ? sv.kite_invalid : sv.kite_ready ? `Logged in${sv.kite_token_day ? ` for ${dateOnly(sv.kite_token_day)}` : ""}` : "Not logged in today, so Indian prices and paper trading are offline." });
  out.push(feedTile(sv));
  out.push({ key: "auto", label: "Automatic daily login", to: "/admin/data",
    state: !sv.auto_login_configured ? "warn" : sv.auto_login.ok === false ? "bad" : sv.auto_login.ok ? "ok" : "warn",
    detail: !sv.auto_login_configured ? "Off" : `${sv.auto_login.message}${sv.auto_login.at ? ` (${ago(sv.auto_login.at)})` : ""}`,
    fix: !sv.auto_login_configured ? "Off. Log in by hand each morning, or set the automatic login variables (setup guide, step 2)." : undefined });
  out.push(aiTile(sv.ai));
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
  if (sv.calendar?.days_left != null) {
    // the holidays on file and the exchange's live list are two facts: with the daily read failing the light says both, so
    // it never reads "OK" beside "The exchange feed isn't answering" in Needs your attention (R12-010)
    const left = sv.calendar.days_left;
    const down = (jobs ?? []).some((j) => j.id === "holidays" && j.state === "bad");
    const state: HealthState = left < 30 ? "bad" : left < 60 || down ? "warn" : "ok";
    out.push({ key: "cal", label: "Exchange holidays", to: "/admin/data", state,
      detail: down ? `Holidays on file for ${left} more days · live feed down` : `Known for ${left} more days` });
  }
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
  const s = Object.fromEntries(services(ov, jobs).map((x) => [x.key, x]));
  if (s.kite.state === "bad") out.push({ text: `Broker data (India): ${s.kite.detail}`, to: "/admin/data", label: "Data and jobs", bad: true });
  if (s.auto.state === "bad") out.push({ text: `The automatic broker login failed: ${sv.auto_login.message}`, to: "/admin/data", label: "Data and jobs", bad: true });
  if (s.feed.state !== "ok") out.push({ text: `Live price feed: ${s.feed.detail}.`, to: "/admin/data", label: "Data and jobs", bad: false });
  const aiKeys = sv.ai.filter((a) => a.configured);
  const aiDown = aiKeys.filter((a) => !aiUp(a));
  if (!aiKeys.length) out.push({ text: "No AI keys are set, so the idea builder and research reads are off.", to: "/admin/system", label: "System", bad: true });
  // one line per provider that can't answer, with the provider's own reason (status code and message), so a rejected
  // key reads differently from a fault on our side (R5O-016)
  for (const a of aiDown) {
    const why = oneLine(a.state_text || a.last_error || "not answering");
    out.push({ text: `AI, ${a.label}: ${why.text}`, ...(why.full ? { full: `AI, ${a.label}: ${why.full}` } : {}), to: "/admin/system", label: "System", bad: false });
  }
  if (aiDown.length && aiDown.length === aiKeys.length) out.push({ text: "No AI provider is answering, so the idea builder and research reads are off.", to: "/admin/system", label: "System", bad: true });
  if (s.mail?.state === "bad") out.push({ text: "Alert emails can't be sent yet: no email service (Resend, Brevo or SMTP) is set up on the server.", to: "/admin/system", label: "System", bad: true });
  // only the errors since this server started are "since the last restart"; ones kept from before it aren't news (R7O-006)
  const errs = errorCounts(sv);
  if (errs.since) out.push({ text: `${plural(errs.since, "server error")} since the last restart.`, to: "/admin/system", label: "System", bad: false });
  const pending = (reported?.entries ?? []).filter((r) => r.hidden_by !== "admin").length;
  if (pending) out.push({ text: `${pending} library entr${pending > 1 ? "ies were" : "y was"} reported by users.`, to: "/admin/quality", label: "Quality", bad: false });
  for (const j of jobs ?? []) {
    if (j.state !== "bad") continue;
    // the holidays read failing isn't holidays missing: said the way the Services light says it (R12-010)
    const text = j.id === "holidays" && s.cal ? `Exchange holidays: ${s.cal.detail.replace(/^Holidays/, "holidays")}. ${j.error}` : `${j.name}: ${j.error}`;
    out.push({ text, to: "/admin/data", label: "Data and jobs", bad: false });
  }
  // feeds on "Check": never run, or only partly read (R5O-016: seven sat on "Not run yet" without a word here). A job
  // switched off on purpose isn't listed.
  const waiting = (jobs ?? []).filter((j) => j.state === "warn" && j.schedule !== "Off");
  if (waiting.length) out.push({ text: `${plural(waiting.length, "data feed")} on Check: ${waiting.map((j) => `${j.name} (${jobDetail(j).toLowerCase()})`).join(", ")}.`,
    to: "/admin/data", label: "Data and jobs", bad: false });
  if (s.cal && s.cal.state !== "ok" && (sv.calendar?.days_left ?? 0) < 60) out.push({ text: `Exchange holidays are only known for ${sv.calendar!.days_left} more days.`, to: "/admin/data", label: "Data and jobs", bad: false });
  const invoice = invoiceWarning(sv.invoice_seller);
  if (invoice) out.push({ text: invoice, to: "/admin/money", label: "Money", bad: sv.billing_enabled });
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

/** A job's line on Overview: its problem, or when it last ran; "Running" first while it runs, as Data and jobs says it
 * (R7O-006: "Running" on one page and "OK" on the other for the same breadth run). */
const jobDetail = (j: JobRow): string => {
  const base = j.error ? j.error : j.last_run ? `Last run ${ago(j.last_run)}` : j.schedule === "Off" ? "Off" : "Not run yet";
  return j.running ? `Running · ${base}` : base;
};

/** The server errors listed: those since this server started, and those kept from before it (the list survives a
 * restart). A server that doesn't say when it started has every one counted as kept, never as "since the restart". */
export function errorCounts(sv: { recent_errors?: { at: string }[]; server_started_at?: string | null }): { since: number; before: number } {
  const all = sv.recent_errors ?? [];
  const start = sv.server_started_at ? Date.parse(sv.server_started_at) : NaN;
  if (!Number.isFinite(start)) return { since: 0, before: all.length };
  const since = all.filter((e) => Date.parse(e.at) >= start).length;
  return { since, before: all.length - since };
}

/** A light for every service and every data feed. */
export function lights(ov: Overview | null, jobs: JobRow[] | null): { services: Light[]; feeds: Light[] } {
  if (!ov) return { services: [], feeds: [] };
  const feeds: Light[] = (jobs ?? []).map((j) => ({ key: j.id, label: j.name, state: j.state, detail: jobDetail(j), to: "/admin/data" }));
  return { services: services(ov, jobs).map(({ fix: _fix, ...l }) => l), feeds };
}

export { jobDetail };
