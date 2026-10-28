import type { HealthState } from "../../components/kit";
import { IST, ago, dateOnly, fmtDate, istToday, quoteAt } from "../../lib/format";
import { aiCountText } from "../../lib/connection";
import { reconnectAt } from "../../lib/dataBack";
import type { AIRow, InvoiceSeller, JobRow, Overview, Reported } from "./AdminContext";

/* One reading of the server's status for all of Admin: Overview's lights and "Needs your attention", the rows on Data and
 * jobs and on System all come from services() below, so two pages can never tell the same fact two ways. */

export type Attention = { text: string; to: string; label: string; bad: boolean; /** the whole text, when `text` was cut to one line */ full?: string };

/** A provider's own error on one line: its first sentence, cut at `max` characters, so a long message with an
 * unbreakable link in it can't push a phone's page sideways (R10O-001). The whole text stays in `full` for a tooltip. */
export function oneLine(text: string, max = 120): { text: string; full?: string } {
  const flat = String(text ?? "").replace(/\s+/g, " ").trim();
  const first = flat.match(/^.*?[.!?](?=\s|$)/)?.[0] ?? flat;
  // cut at a word, never inside one (DJ-007: "…currently experie…")
  const head = first.slice(0, max - 1), space = head.lastIndexOf(" ");
  const cut = first.length > max ? `${(space > max / 2 ? head.slice(0, space) : head).replace(/[\s,;:(]+$/, "")}…` : first;
  return cut === flat ? { text: flat } : { text: cut, full: flat };
}
/** A job's raw network error as one plain line, the raw text kept in `full` for the tooltip (R18-010: "HTTPSConnectionPool(host='api.kite.trade'…) Read timed out"). */
export function plainError(text: string | null | undefined): { text: string; full?: string } {
  const flat = String(text ?? "").replace(/\s+/g, " ").trim();
  const m = /HTTPSConnectionPool\(host='([^']+)'/.exec(flat);
  if (!m) return { text: flat };
  const who = /kite/i.test(m[1]) ? "Kite" : "The data provider";
  const why = /timed out/i.test(flat) ? " didn't answer in time" : " couldn't be reached";
  return { text: `${flat.slice(0, m.index)}${who}${why}`, full: flat };
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
  // with only options sessions the feed is shut and that is fine: said as one plain fact, not "OK" beside "Not needed"
  // (R24-011: "Live price feed OK / Not needed: 2 options paper sessions running…" read as a contradiction)
  const detail = sv.feed_connected ? [`Connected${india ? `, ${plural(india, "India paper session")} running` : ""}`, opts].filter(Boolean).join(" · ")
    : india ? [`Not connected, with ${plural(india, "India paper session")} running`, opts].filter(Boolean).join(" · ")
    : options ? `Not connected, and no session needs it: the ${plural(options, "options paper session")} running${across} read quotes every few seconds instead`
    : "Idle: no India paper sessions running";
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
  // the denominator is the providers with a key, said as System says it ("12 of 13 providers set up") when some have none (R8O-008); one denominator, not two ("12" beside "12 of 13"), R7M-008; Settings' Connection check words it the same way (aiCountText)
  return { key: "ai", label: "AI providers", state, to: "/admin/system",
    detail: [aiCountText(working, keys.length, ai.length), ...notes].join(" · ") };
}

/** The invoice seller details still empty, said for Overview and Money (R7M-001): until a GSTIN is set every invoice is a
 * plain one that says the supplier is not registered under GST, with the Plans page promising otherwise. */
export function invoiceWarning(s: InvoiceSeller | undefined): string | null {
  if (!s || s.complete) return null;
  const all = s.missing.length >= 4;
  return `${all ? "The invoice seller details are empty" : `The invoice seller details are missing the ${s.missing.join(", ")}`}. `
    + (s.gst ? "Invoices carry GST, but are incomplete without them."
      : "Until the GSTIN is set, every invoice is a plain one that says the supplier isn't registered under GST and charges none, and the Plans page says no GST is added. If you are registered, fill the details in before the first payment.");
}

/** The next automatic data login with its day, as the top banner says it: "Sun 25 Oct, 08:00 IST" (DJ-003: "08:00 IST"
 * didn't say which day). */
export const loginAt = (iso: string): string => reconnectAt({ closed: null, back_at: iso }, "Asia/Kolkata") ?? quoteAt(iso, IST);

/** The alert-email row's words, without promising Telegram when the server has none (DJ-033). */
export function mailFix(fix: string | undefined, telegram: boolean | undefined): string | undefined {
  if (!fix || telegram !== false) return fix;
  return fix.replace(", plus your phone or Telegram if set in Account.", ", plus your phone if set in Account (Telegram isn't set up on the server).")
    .replace("Until then alerts reach only your phone or Telegram.", "Until then alerts reach only your phone.");
}

/** Brevo's sends today against what its plan has left today (DJ-034), or null when Brevo said nothing. `low`: under a
 * tenth of the day's sends left. */
export function quotaLine(q: NonNullable<Overview["server"]["admin_alerts"]>["quota"]): { text: string; sent: string | null; left: string | null; low: boolean } | null {
  if (!q || (q.sent_today == null && q.left_today == null)) return null;
  const sent = q.sent_today != null ? `${plural(q.sent_today, "email")} sent today` : null;
  const left = q.left_today != null ? `${q.left_today.toLocaleString("en-IN")} left of today's limit${q.plan ? ` (Brevo's ${q.plan} plan)` : ""}` : null;
  const total = (q.sent_today ?? 0) + (q.left_today ?? 0);
  return { text: [sent, left].filter(Boolean).join(", "), sent, left, low: q.left_today != null && total > 0 && q.left_today < total / 10 };
}

/** Invoiced revenue by currency in one line: "₹6,990 · $16" (DJ-004). */
export function revenueText(by: Record<string, number>, fmt: (v: number, c: string) => string = (v, c) => `${c} ${v.toLocaleString("en-IN")}`): string {
  const rows = Object.entries(by).sort(([a], [b]) => (a === "INR" ? -1 : b === "INR" ? 1 : a.localeCompare(b)));
  return rows.length ? rows.map(([c, v]) => fmt(v, c)).join(" · ") : fmt(0, "INR");
}

/** Every service's light, worded once. */
export function services(ov: Overview | null, jobs: JobRow[] | null = null): Service[] {
  if (!ov) return [];
  const sv = ov.server;
  const out: Service[] = [];
  // India shut today anyway (a weekend or an exchange holiday): a logged-out broker is expected, said as the top banner
  // says it, not an amber Check that teaches the owner to ignore amber (DJ-003)
  const closed = !sv.kite_ready ? sv.data_note?.closed ?? null : null;
  const shut = closed ? `Markets closed ${closed === "weekend" ? "for the weekend" : "today for an exchange holiday"}${sv.auto_login_next ? `; next login ${loginAt(sv.auto_login_next)}` : ""}.` : "";
  // before today's automatic login the data is offline every morning (Zerodha's own reset ends yesterday's login): that is
  // a wait, not a Problem to fix (R49-008: "Problem … Not logged in today" at 06:48, logged in by itself at 08:03)
  const dueToday = !sv.kite_ready && !!sv.auto_login_next && sv.auto_login_next.slice(0, 10) === istToday() && sv.auto_login.ok !== false;
  out.push({ key: "kite", label: "Broker data (India)", state: sv.kite_ready || closed ? "ok" : dueToday ? "warn" : "bad", to: "/admin/data",
    detail: sv.kite_ready ? `Logged in${sv.kite_token_day ? ` for ${dateOnly(sv.kite_token_day)}` : ""}`
      : closed ? shut
      : dueToday ? `Not logged in yet today. The automatic login at ${quoteAt(sv.auto_login_next!, IST)} logs in again; nothing to do.`
      : sv.kite_invalid ? sv.kite_invalid : "Not logged in today, so Indian prices and paper trading are offline." });
  out.push(feedTile(sv));
  // a login that worked but was cancelled by Zerodha since is not "OK" beside the broker's Problem (R46-001)
  const undone = !!sv.kite_invalid && sv.auto_login.ok === true;
  const next = sv.auto_login_next ? ` Next automatic login: ${loginAt(sv.auto_login_next)}.` : "";
  out.push({ key: "auto", label: "Automatic daily login", to: "/admin/data",
    state: !sv.auto_login_configured ? "warn" : sv.auto_login.ok === false ? "bad" : undone && !closed ? "warn" : sv.auto_login.ok ? "ok" : "warn",
    detail: !sv.auto_login_configured ? "Off"
      : undone && closed ? `OK: ${shut}`
      : undone ? `Logged in${sv.auto_login.at ? ` ${ago(sv.auto_login.at)}` : ""}, but Zerodha has cancelled that login since.${next}`
      // the next run is said every time, as every other job's is (R60-010)
      // the sentence's full stop comes after the time, never before it ("Logged in to Kite. (14 h ago)."), and the hour it went through is
      // said with what started it, so 14 hours ago against an 08:00 schedule is explained (LIVE1C-016)
      : `${sv.auto_login.message.replace(/\.$/, "")}${sv.auto_login.at ? ` ${ago(sv.auto_login.at)} (${quoteAt(sv.auto_login.at, IST)}${sv.auto_login.how ? `, ${sv.auto_login.how}` : ""})` : ""}${next ? `.${next}` : ""}`,
    fix: !sv.auto_login_configured ? "Off. Log in by hand each morning, or set the automatic login variables (setup guide, step 2)." : undefined });
  out.push(aiTile(sv.ai));
  if (sv.admin_alerts) {
    const a = sv.admin_alerts;
    const quota = quotaLine(a.quota);
    out.push({ key: "mail", label: "Alert emails", state: !a.email_ready ? "bad" : quota?.low ? "warn" : "ok", to: "/admin/system",
      detail: a.email_ready ? `${a.via ? `Sent through ${a.via}` : "Ready"}${quota ? ` · ${quota.text}` : ""}` : "Not set up: no email service on the server",
      fix: a.email_ready ? `Emailed to ${a.to.join(", ")}${a.via ? ` through ${a.via}` : ""}${quota ? `; ${quota.text}` : ""}, plus your phone or Telegram if set in Account.`
        : "No email service is set up on the server. Add one in Railway: RESEND_API_KEY (a free account at resend.com made with this address), "
          + "or BREVO_API_KEY, or SMTP_HOST, SMTP_USER and SMTP_PASSWORD. Until then alerts reach only your phone or Telegram." });
  }
  out.push({ key: "co", label: "US company data", state: sv.research?.finnhub ? "ok" : "warn", to: "/admin/system",
    detail: sv.research?.finnhub ? "Key is set" : "No key",
    fix: sv.research?.finnhub ? undefined : "No key. Add the company-data key in Railway for US company pages (setup guide, step 6). India needs no key." });
  // live keys and no payment event ever received: a first real payment would not upgrade the plan by itself, so Check, not OK (LIVE1C-008)
  const noHook = sv.billing_enabled && sv.billing_hook?.mode === "live" && !sv.billing_hook.last_at;
  out.push({ key: "pay", label: "Payments", state: sv.billing_enabled ? (noHook ? "warn" : "ok") : "warn",
    detail: sv.billing_enabled ? (noHook ? "Connected, but Razorpay has never sent a payment event: send a test event before the first payment" : "Connected") : "Not set up", to: "/admin/money" });
  if (sv.calendar?.days_left != null) {
    // the holidays on file and the exchange's live list are two facts: with the daily read failing the light says both, so
    // it never reads "OK" beside "The exchange feed isn't answering" in Needs your attention (R12-010)
    const left = sv.calendar.days_left;
    const down = (jobs ?? []).some(holidaysDown);
    const state: HealthState = left < 30 ? "bad" : left < 60 || down ? "warn" : "ok";
    out.push({ key: "cal", label: "Exchange holidays", to: "/admin/data", state,
      detail: down ? `Holidays on file for ${left} more days · live feed down` : `Known for ${left} more days` });
  }
  return out;
}

/** The exchange holidays read failing: a Problem from an older server, or the Check it is while the holidays on file still
 * cover the weeks ahead (R13-012: "Problem, couldn't reach the exchange" with 83 days on file). Said once, in the
 * Services light's words, never also among the feeds on Check. */
export function holidaysDown(j: { id: string; state: string; error?: string | null }): boolean {
  return j.id === "holidays" && (j.state === "bad" || (j.state === "warn" && !!j.error));
}

/** One service by its key, for the page that shows it as a row. */
export function service(ov: Overview | null, key: string): Service | undefined {
  return services(ov).find((s) => s.key === key);
}

/** A provider's error that clears by itself: a server fault (5xx), a timeout, a busy or rate-limited answer. A rejected key or a
 * missing model is not one. */
export const passingFault = (text: string | null | undefined): boolean =>
  /\b(?:server error|5\d\d|timed out|time ?out|overloaded|busy|high demand|rate.?limit|try again|unavailable|temporar\w*)/i.test(String(text ?? ""))
  && !/\b(?:40[0-9]|invalid|rejected|unauthori[sz]ed|forbidden|key)\b/i.test(String(text ?? ""));

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
  // a provider out of its free quota or paused resets on its own: one line for them all, nothing to do (DJ-002: four such
  // lines buried the items the owner must act on); a failing one keeps its own line, with its own reason
  const waits = aiDown.filter((a) => a.result === "quota" || a.result === "paused" || (a.result === undefined && a.quota_used));
  // a provider that is out of quota, resting, or failed on a passing fault of its own (a 5xx, a timeout, a busy server) resets by itself:
  // the AI light on Services says so and System lists each; Needs your attention holds only what the owner must do (LIVE1C-003:
  // "paused … nothing to do" and "Gemini: server error 503" beside an invoice that did need a look)
  const act = aiDown.filter((a) => !waits.includes(a) && !passingFault(a.state_text || a.last_error));
  for (const a of act) {
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
    if (j.state !== "bad" && !holidaysDown(j)) continue;
    // the holidays read failing isn't holidays missing: said the way the Services light says it (R12-010)
    const err = plainError(j.error);
    const text = j.id === "holidays" && s.cal ? `Exchange holidays: ${s.cal.detail.replace(/^Holidays/, "holidays")}. ${err.text}` : `${j.name}: ${err.text}`;
    out.push({ text, ...(err.full ? { full: `${j.name}: ${err.full}` } : {}), to: "/admin/data", label: "Data and jobs", bad: false });
  }
  // feeds on "Check": never run, or only partly read (R5O-016: seven sat on "Not run yet" without a word here). A job
  // switched off on purpose isn't listed.
  const waiting = (jobs ?? []).filter((j) => j.state === "warn" && j.schedule !== "Off" && !holidaysDown(j));
  // each feed's words as Data and jobs writes them, not lowercased (DJ-007: "not read: index provider:")
  if (waiting.length) out.push({ text: `${plural(waiting.length, "data feed")} on Check: ${waiting.map((j) => `${j.name} (${jobDetail(j)})`).join("; ")}.`,
    to: "/admin/data", label: "Data and jobs", bad: false });
  // said once: when the holidays job's line above already speaks for them, not again here (R45A-017)
  const holidaysSaid = out.some((o) => o.text.startsWith("Exchange holidays"));
  if (!holidaysSaid && s.cal && s.cal.state !== "ok" && (sv.calendar?.days_left ?? 0) < 60) out.push({ text: `Exchange holidays are only known for ${sv.calendar!.days_left} more days.`, to: "/admin/data", label: "Data and jobs", bad: false });
  // official rate and rule sources: one unread for days, or a change waiting for a look, is named here, not only on
  // Quality (R50-008: three sources unread for 16 days, Overview silent)
  const rw = sv.rules_watch;
  if (rw?.failing.length) out.push({ text: `Rate and rule sources unread: ${rw.failing.map((f) => `${f.name} (${f.fails} runs in a row)`).join(", ")}.`,
    to: "/admin/quality", label: "Quality", bad: false });
  if (rw?.pending.length) out.push({ text: `Rate and rule sources changed, waiting for a look: ${rw.pending.join(", ")}.`, to: "/admin/quality", label: "Quality", bad: false });
  // the whole-market audit's companies with a number that disagrees with its source (R50-008)
  const mm = sv.audit_mismatches ?? {};
  // with when those rows were checked: a mismatch from weeks ago isn't today's (DJ-026)
  const checkedOn = (r: "IN" | "US") => { const c = sv.audit_checked?.[r]; if (!c) return "";
    const a = fmtDate(c.oldest, { year: false, tz: IST }), b = fmtDate(c.newest, { year: false, tz: IST });
    return a === b ? ` (checked ${a})` : ` (checked ${a} to ${b})`; };
  const mmText = (["IN", "US"] as const).filter((r) => mm[r]).map((r) => `${mm[r]} in ${r === "IN" ? "India" : "the US"}${checkedOn(r)}`);
  if (mmText.length) out.push({ text: `The whole-market audit has companies whose numbers disagree with their source: ${mmText.join(", ")}.`, to: "/admin/quality", label: "Quality", bad: false });
  const invoice = invoiceWarning(sv.invoice_seller);
  if (invoice) out.push({ text: invoice, to: "/admin/money", label: "Money", bad: sv.billing_enabled });
  if (sv.billing_enabled && s.pay.state === "warn") out.push({ text: `Payments: ${s.pay.detail}.`, to: "/admin/money", label: "Money", bad: false });
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
  const base = j.error ? plainError(j.error).text : j.last_run ? `Last run ${ago(j.last_run)}` : j.schedule === "Off" ? "Off" : "Not run yet";
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

/** The server errors as groups (DJ-035: 22 of 24 rows the same "RemoteProtocolError … contextlib.py:158 in __exit__"): one row
 * per kind of error and place, newest first, with how many and the newest's ref; a known upstream fault said in plain words. */
export type ErrorGroup = { key: string; count: number; at: string; ref: string; path: string; error: string; where: string; plain: string | null };
export function groupErrors(rows: { ref: string; at: string; method: string; path: string; error: string; where: string }[]): ErrorGroup[] {
  const by = new Map<string, ErrorGroup>();
  for (const e of rows) {
    const kind = String(e.error ?? "").split(":")[0].trim();
    const key = `${kind}|${e.where}`;
    const g = by.get(key);
    if (!g) by.set(key, { key, count: 1, at: e.at, ref: e.ref, path: `${e.method} ${e.path}`, error: e.error, where: e.where, plain: plainServerError(e.error) });
    else {
      g.count += 1;
      if (Date.parse(e.at) > Date.parse(g.at)) Object.assign(g, { at: e.at, ref: e.ref, path: `${e.method} ${e.path}`, error: e.error });
    }
  }
  return [...by.values()].sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
}

/** A known upstream fault in words, or null: the raw text stays beside it. */
export function plainServerError(text: string): string | null {
  const t = String(text ?? "");
  if (/RemoteProtocolError|Server disconnected|ConnectionResetError|connection (was )?(reset|closed)/i.test(t))
    return "A connection to an outside service (usually the database) dropped in the middle of a request; the user was asked to try again.";
  if (/ReadTimeout|timed out/i.test(t)) return "An outside service (usually the database) didn't answer in time.";
  if (/PoolTimeout/i.test(t)) return "Every database connection was busy, so the request waited too long.";
  return null;
}
