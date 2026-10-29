import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { fmtDateTime } from "../../lib/format";
import { Card, CardHead, DataTable, Disclosure, EmptyState, Skeleton, StatusList, StatusRow, type Column } from "../../components/kit";
import { useAdmin } from "./AdminContext";
import { AIPanel } from "./AIPanel";
import { errorCounts, groupErrors, mailFix, service, type ErrorGroup } from "./attention";
import { PlatformPanel } from "./PlatformPanel";
import { APP_BUILD, buildLine } from "../../lib/buildInfo";
import { IST, ago, when } from "../../lib/format";

type FilingCheck = { ok: boolean; symbol: string; count?: number; error?: string; latest?: { at: string; label: string; subject: string }[];
  documents_found?: number; document?: { ok: boolean; title: string; kind: string; chars?: number; error?: string } | null };

// grouped, and in India time as the rest of Admin (DJ-035: UTC here, IST elsewhere, and 22 rows of the same error)
// each error is a two-line row: what happened in words, then when and where (Ref · Request · Newest); the program's own text and its place
// in the code are behind Details, so nothing hides behind a fade at the edge (LIVE1C-022, LIVE1C-024)
const ERRORS: Column<ErrorGroup>[] = [
  { key: "err", header: "Error", rowHeader: true, wrap: true, cell: (x) => (
    <span className="k-stack tight">
      <b className="k-small">{x.plain ?? "An unexpected error in the server."}</b>
      <span className="k-note k-muted">Ref <span className="adm-mono">{x.ref}</span> · <span className="adm-mono adm-break">{x.path}</span> · newest {fmtDateTime(x.at, { seconds: true, zone: true, tz: IST })}</span>
      <Disclosure summary="Details" className="adm-err-details"><span className="adm-cell adm-break">{x.error}</span><br /><span className="adm-mono adm-break k-muted">{x.where}</span></Disclosure>
    </span>) },
  { key: "n", header: "Times", numeric: true, cell: (x) => x.count },
];

type AutoCheck = { name: string; state: "pass" | "warn" | "fail"; detail: string };

/** Whether two builds are the same commit (by their common prefix); null when either isn't known. */
export function sameBuild(a: string | null | undefined, b: string | null | undefined): boolean | null {
  if (!a || !b) return null;
  const n = Math.min(a.length, b.length, 40);
  return n >= 7 ? a.slice(0, n).toLowerCase() === b.slice(0, n).toLowerCase() : null;
}

/** Admin → System: server errors, the other services, AI providers, the feature check, and real prices for the tests. */
export function SystemSection() {
  const { notify, fail, me } = useApp();
  const { ov, reload } = useAdmin();
  const chans = me?.alerts.channels;      // which ways of sending an alert the server has (the user's Settings shows only those)
  const [busy, setBusy] = useState<string | null>(null);
  const [filing, setFiling] = useState<FilingCheck | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);
  // the last automatic check's own filings result, so the row isn't "Not checked" beside a Pass made hours before (DJ-033)
  const [auto, setAuto] = useState<{ at: string; check: AutoCheck } | null>(null);
  useEffect(() => {
    api<{ last: { at: string; checks: AutoCheck[] } | null }>("/admin/platform/last").then((x) => {
      const c = x.last?.checks.find((k) => k.name === "Exchange filings");
      if (x.last && c) setAuto({ at: x.last.at, check: c });
    }).catch(() => {});
  }, []);
  const run = async (key: string, fn: () => Promise<void>) => { setBusy(key); try { await fn(); } catch (e) { fail(e); } finally { setBusy(null); } };
  const sv = ov?.server;
  const co = service(ov, "co"), mail = service(ov, "mail");     // the same lights and words as Overview's
  const testEmail = () => run("mail", async () => {
    const r = await api<{ sent_to: string }>("/admin/alerts/test", { method: "POST" });
    // said on the card too, not only in a toast that can go before it's read (R52-005)
    const msg = `Test email sent to ${r.sent_to} at ${new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}. Check your inbox (and spam).`;
    notify(msg); setSent(msg);
  });
  const reviewLink = () => run("review", async () => {
    const r = await api<{ sent_to: string }>("/admin/review-link", { method: "POST" });
    notify(`A one-time sign-in link for the reviewer was sent to ${r.sent_to}. It expires in an hour.`);
  });
  const sendWeekly = () => run("weekly", async () => {
    const r = await api<{ subject: string; reached: number }>("/admin/weekly/test", { method: "POST" });
    const msg = r.reached ? `"${r.subject}" sent at ${new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}. Check your inbox (and spam).` : "The summary couldn't reach you: set up email or a phone in Account.";
    notify(msg); setSent(msg);
  });
  const checkFilings = () => run("filings", async () => { setFiling(await api<FilingCheck>("/admin/filings/check", { method: "POST" })); });
  const saveFixture = () => run("fixture", async () => {
    setNote("Collecting about two years of prices. This takes a minute or two…");
    const r = await api<Response>("/admin/fixture/prices", { method: "POST", raw: true });
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "real_prices.json.gz"; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    setNote(`Saved real_prices.json.gz: ${r.headers.get("X-Instruments") ?? "?"} instruments, ${Math.round(blob.size / 1024)} KB${Number(r.headers.get("X-Problems")) ? `, ${r.headers.get("X-Problems")} skipped` : ""}. Upload it to GitHub at stratlab/backend/tests/fixtures/real_prices.json.gz.`);
  });
  const errors = groupErrors(sv?.recent_errors ?? []);
  const counted = errorCounts(sv ?? {});

  return (
    <>
      <Card label="Server errors">
        {/* until the status has arrived there is nothing to count: a "0 errors, nothing has crashed" then would be false comfort (R7M-007) */}
        <CardHead title={sv ? `Server errors (${counted.since} since the last restart${counted.before ? `, ${counted.before} kept from before it` : ""})` : "Server errors"}
          info="Crashes newest first: those since the server last started, and the last ones from before it, which are kept across a restart. Users see the ref code in the error message." />
        {!sv ? <Skeleton label="Loading the server errors" lines={2} onRetry={() => { void reload(); }} /> : !errors.length ? <EmptyState title="No server errors">Nothing has crashed since the server last started, and none were kept from before it.</EmptyState>
          : <DataTable label="Server errors" rows={errors} rowKey={(x) => x.key} columns={ERRORS} stack />}
      </Card>

      <Card label="Other services">
        <CardHead title="Other services" />
        {sv && (
          <StatusList label="Other services">
            {chans && <StatusRow state={chans.telegram && chans.email ? "ok" : "warn"} label="Alert channels"
              detail={chans.telegram && chans.email ? "Telegram and email are set up, so users can add them under Settings."
                : `${[!chans.telegram && "Telegram", !chans.email && "Email"].filter(Boolean).join(" and ")} ${!chans.telegram && !chans.email ? "aren't" : "isn't"} set up on the server, so ${!chans.telegram && !chans.email ? "they're" : "it's"} hidden from users' Settings.`} />}
            {co && <StatusRow state={co.state} label={co.label} detail={co.fix ?? co.detail} />}
            {sv.admin_alerts && mail && <StatusRow state={mail.state} label={mail.label} detail={mailFix(mail.fix, chans?.telegram) ?? mail.detail}
              actions={<>
                {sv.admin_alerts.email_ready && <button type="button" className="btn quiet sm" disabled={busy === "mail"} onClick={testEmail}>{busy === "mail" ? "Sending…" : "Send a test email"}</button>}
                {sv.admin_alerts.email_ready && <button type="button" className="btn quiet sm" disabled={busy === "review"} onClick={reviewLink} title="A one-time link that signs the automated reviewer in as you, sent to your own address">{busy === "review" ? "Sending…" : "Email a reviewer sign-in link"}</button>}
                <button type="button" className="btn quiet sm" disabled={busy === "weekly"} onClick={sendWeekly} title={`The summary that goes out every Monday at 9:00 IST, sent now to ${sv.admin_alerts.to.length ? `${sv.admin_alerts.to.length} admin address${sv.admin_alerts.to.length === 1 ? "" : "es"}` : "all admins"}`}>{busy === "weekly" ? "Sending…" : "Send this week's summary now"}</button>
              </>} />}
            {sent && <p className="k-small k-muted" role="status" data-testid="alert-sent">{sent}</p>}
            <StatusRow state={!filing ? (auto ? (auto.check.state === "pass" ? "ok" : auto.check.state === "warn" ? "warn" : "bad") : "warn") : filing.ok ? "ok" : "bad"}
              word={filing ? undefined : auto ? (auto.check.state === "pass" ? "Pass" : auto.check.state === "warn" ? "Check" : "Fail") : "Not checked"} label={`Exchange filings${filing ? ` (${filing.symbol})` : ""}`}
              detail={!filing ? (auto ? `In the check ${ago(auto.at)}: ${auto.check.detail} Press the button to ask again now.` : "Press the button to ask the exchange for a company's filings.") : filing.ok
                ? `${filing.count} filings in the last year. Latest: ${(filing.latest ?? []).map((l) => `${l.at.slice(0, 10)} ${l.label}`).join("; ") || "none"}`
                : `${filing.error} The exchange sometimes blocks cloud servers; if this keeps failing, the BSE feed can be added as a fallback.`}
              actions={<button type="button" className="btn quiet sm" disabled={busy === "filings"} onClick={checkFilings}>{busy === "filings" ? "Asking the exchange…" : "Check filings feed"}</button>} />
            {filing?.ok && <StatusRow state={filing.document?.ok ? "ok" : "warn"} label="Company documents (deep dive)"
              detail={!filing.document ? `No presentation or call transcript among ${filing.symbol}'s filings to try.`
                : filing.document.ok ? `Read "${filing.document.title}" (${filing.document.kind}): ${filing.document.chars?.toLocaleString("en-IN")} characters of text. ${filing.documents_found} documents found.`
                  : `Couldn't read "${filing.document.title}": ${filing.document.error}`} />}
          </StatusList>
        )}
      </Card>

      <Card label="Build">
        <CardHead title="Build" info="Which code is running: the commit and branch each host deployed, when it was built if the host says, and when the server last started." />
        <StatusList label="Build">
          {/* a word that says something (DJ-037: the old one, Known, said nothing): whether the web app is the server's build */}
          <StatusRow state={sv?.build?.sha ? "ok" : "warn"} word={sv?.build?.sha ? "Running" : "Not set"} label="Server" detail={sv ? buildLine(sv.build, (iso) => when(iso, "Asia/Kolkata", true, true)) : "Loading…"} />
          <StatusRow state={!APP_BUILD.sha ? "warn" : sameBuild(APP_BUILD.sha, sv?.build?.sha) === false ? "warn" : "ok"}
            word={!APP_BUILD.sha ? "Not set" : sameBuild(APP_BUILD.sha, sv?.build?.sha) === true ? "Same as the server" : sameBuild(APP_BUILD.sha, sv?.build?.sha) === false ? "Not the server's" : "Deployed"}
            label="Web app" detail={buildLine(APP_BUILD, (iso) => when(iso, "Asia/Kolkata", true, true))} />
        </StatusList>
      </Card>

      <AIPanel />
      <PlatformPanel />

      <Card label="Real prices for testing">
        <CardHead title="Real prices for testing" info="About two years of daily prices for the indices and a few stocks in each market, so the test suite checks the tools on real market behaviour. Prices only, no user data. Refresh it every few months."
          actions={<button type="button" className="btn quiet sm" disabled={busy === "fixture"} onClick={saveFixture}>{busy === "fixture" ? "Collecting prices…" : "Save real prices"}</button>} />
        {note && <p className="k-small k-muted" role="status">{note}</p>}
      </Card>
    </>
  );
}
