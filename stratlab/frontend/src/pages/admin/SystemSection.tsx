import { useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { Card, CardHead, DataTable, EmptyState, StatusList, StatusRow, type Column } from "../../components/kit";
import { useAdmin, type ServerError } from "./AdminContext";
import { AIPanel } from "./AIPanel";
import { service } from "./attention";
import { PlatformPanel } from "./PlatformPanel";

type FilingCheck = { ok: boolean; symbol: string; count?: number; error?: string; latest?: { at: string; label: string; subject: string }[];
  documents_found?: number; document?: { ok: boolean; title: string; kind: string; chars?: number; error?: string } | null };

const ERRORS: Column<ServerError>[] = [
  { key: "ref", header: "Ref", rowHeader: true, cell: (x) => <span className="adm-mono">{x.ref}</span> },
  { key: "at", header: "When", cell: (x) => new Date(x.at).toLocaleString("en-GB") },
  { key: "req", header: "Request", wrap: true, cell: (x) => <span className="adm-mono">{x.method} {x.path}</span> },
  { key: "err", header: "Error", wrap: true, cell: (x) => <span className="adm-cell">{x.error}</span> },
  { key: "where", header: "Where", wrap: true, cell: (x) => <span className="adm-mono">{x.where}</span> },
];

/** Admin → System: server errors, the other services, AI providers, the feature check, and real prices for the tests. */
export function SystemSection() {
  const { notify, fail, me } = useApp();
  const { ov } = useAdmin();
  const chans = me?.alerts.channels;      // which ways of sending an alert the server has (the user's Settings shows only those)
  const [busy, setBusy] = useState<string | null>(null);
  const [filing, setFiling] = useState<FilingCheck | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const run = async (key: string, fn: () => Promise<void>) => { setBusy(key); try { await fn(); } catch (e) { fail(e); } finally { setBusy(null); } };
  const sv = ov?.server;
  const co = service(ov, "co"), mail = service(ov, "mail");     // the same lights and words as Overview's
  const testEmail = () => run("mail", async () => {
    const r = await api<{ sent_to: string }>("/admin/alerts/test", { method: "POST" });
    notify(`Test email sent to ${r.sent_to}. Check your inbox (and spam).`);
  });
  const reviewLink = () => run("review", async () => {
    const r = await api<{ sent_to: string }>("/admin/review-link", { method: "POST" });
    notify(`A one-time sign-in link for the reviewer was sent to ${r.sent_to}. It expires in an hour.`);
  });
  const sendWeekly = () => run("weekly", async () => {
    const r = await api<{ subject: string; reached: number }>("/admin/weekly/test", { method: "POST" });
    notify(r.reached ? `"${r.subject}" sent. Check your inbox (and spam).` : "The summary couldn't reach you: set up email or a phone in Account.");
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
  const errors = sv?.recent_errors ?? [];

  return (
    <>
      <Card label="Server errors">
        <CardHead title={`Server errors (${errors.length})`} info="Crashes since the server last started, newest first. Users see the ref code in the error message." />
        {!errors.length ? <EmptyState title="No server errors">Nothing has crashed since the server last started.</EmptyState>
          : <DataTable label="Server errors" rows={errors} rowKey={(x) => x.ref} columns={ERRORS} />}
      </Card>

      <Card label="Other services">
        <CardHead title="Other services" />
        {sv && (
          <StatusList label="Other services">
            {chans && <StatusRow state={chans.telegram && chans.email ? "ok" : "warn"} label="Alert channels"
              detail={chans.telegram && chans.email ? "Telegram and email are set up, so users can add them under Settings."
                : `${[!chans.telegram && "Telegram", !chans.email && "Email"].filter(Boolean).join(" and ")} ${!chans.telegram && !chans.email ? "aren't" : "isn't"} set up on the server, so ${!chans.telegram && !chans.email ? "they're" : "it's"} hidden from users' Settings.`} />}
            {co && <StatusRow state={co.state} label={co.label} detail={co.fix ?? co.detail} />}
            {sv.admin_alerts && mail && <StatusRow state={mail.state} label={mail.label} detail={mail.fix ?? mail.detail}
              actions={<>
                {sv.admin_alerts.email_ready && <button type="button" className="btn quiet sm" disabled={busy === "mail"} onClick={testEmail}>{busy === "mail" ? "Sending…" : "Send a test email"}</button>}
                {sv.admin_alerts.email_ready && <button type="button" className="btn quiet sm" disabled={busy === "review"} onClick={reviewLink} title="A one-time link that signs the automated reviewer in as you, sent to your own address">{busy === "review" ? "Sending…" : "Email a reviewer sign-in link"}</button>}
                <button type="button" className="btn quiet sm" disabled={busy === "weekly"} onClick={sendWeekly} title="The summary that goes out every Monday at 9:00 IST">{busy === "weekly" ? "Sending…" : "Send this week's summary now"}</button>
              </>} />}
            <StatusRow state={!filing ? "warn" : filing.ok ? "ok" : "bad"} word={filing ? undefined : "Not checked"} label={`Exchange filings${filing ? ` (${filing.symbol})` : ""}`}
              detail={!filing ? "Press the button to ask the exchange for a company's filings." : filing.ok
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
