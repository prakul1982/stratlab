import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { fmtDate, fmtDateTime, IST, safeHref } from "../../lib/format";
import { Card, CardHead, CheckField, ConfirmDialog, DataTable, EmptyState, Light, Skeleton, type Column, type HealthState } from "../../components/kit";
import { useAdmin } from "./AdminContext";

/* Admin → Social (social103, owner 28 Nov: "daily posting on X and LinkedIn fully automated; I have no time to post"): connect each account
 * (the network's own sign-in, done by the server: no token ever reaches this page), switch its daily post on, see the next post and the
 * last ones, and send one now to test. */

export type SocialNet = {
  key: "x" | "linkedin"; name: string; configured: boolean; connected: boolean; enabled: boolean; expires_at: string | null; days_left: number | null;
  problem: string | null; failed: { at: string | null; status: string; error: string | null; day: string | null } | null;
  vars: string[]; callback: string; scopes: string; account: string | null; connected_at: string | null; renews: boolean;
  next: { at: string; parts: string[]; theme: string; link: string } | null; next_note: string | null;
  /** X only (pay-per-use): this month's posts and replies, the estimated cost in dollars, the monthly cap and why posting is paused */
  month?: { month: string; posts: number; replies: number; cost_usd: number; cap: number; paused: string | null; usd_inr: number | null;
    rates: { link_post: number; plain_post: number; reply: number } };
  thread?: boolean;
};
export type SocialPost = { id: string; net: string; name: string; kind: "daily" | "manual"; day: string; at: string; updated: string | null; theme: string | null;
  region: string | null; link: string | null; status: "sending" | "posted" | "failed" | "unknown"; attempts: number; url: string | null; error: string | null;
  parts: number; text: string };
export type SocialState = { networks: SocialNet[]; posts: SocialPost[]; vault_ready: boolean; schedule: string; offline: boolean };

const LIMIT: Record<SocialNet["key"], number> = { x: 280, linkedin: 1300 };
const RESULT: Record<string, string> = {
  connected: "connected. Switch its daily post on when you're ready.",
  denied: "wasn't connected: the sign-in was cancelled on its page.",
  expired: "wasn't connected: the sign-in took too long or was already used. Press Connect again.",
  failed: "wasn't connected: the network refused the sign-in. The reason is on its card.",
};
const STATUS: Record<SocialPost["status"], { word: string; state: HealthState }> = {
  posted: { word: "Posted", state: "ok" }, sending: { word: "Sending", state: "warn" }, failed: { word: "Failed", state: "bad" }, unknown: { word: "Not sure it went", state: "warn" },
};

/** A network's light and line: not set up, not connected, connected (and until when), with any problem. */
export function netState(n: SocialNet): { state: HealthState; word: string; detail: string } {
  if (!n.configured) return { state: "warn", word: "Not set up", detail: `Add ${n.vars.join(" and ")} in Railway → Variables, then redeploy.` };
  if (n.problem && !n.connected) return { state: "bad", word: "Not connected", detail: n.problem };
  if (!n.connected) return { state: "warn", word: "Not connected", detail: `Press Connect ${n.name}: you sign in on ${n.name}'s own page and come back here.` };
  const who = `Connected as ${n.account ?? "your account"}${n.connected_at ? ` since ${fmtDate(n.connected_at, { tz: IST })}` : ""}.`;
  const until = n.renews ? " Stays connected: StratLab renews the sign-in by itself."
    : n.expires_at ? ` Sign-in ends ${fmtDate(n.expires_at, { tz: IST })}${n.days_left !== null ? ` (${n.days_left < 0 ? "ended" : `${n.days_left} day${n.days_left === 1 ? "" : "s"} left`})` : ""}: reconnect before then.` : "";
  const ending = !n.renews && n.days_left !== null && n.days_left <= 7;
  if (n.problem) return { state: "bad", word: "Problem", detail: `${who}${until} ${n.problem}` };
  return { state: ending ? "warn" : "ok", word: n.enabled ? "Posting daily" : "Connected, off", detail: `${who}${until}` };
}

function NetCard({ n, schedule, busy, act }: { n: SocialNet; schedule: string; busy: string | null; act: (key: string, fn: () => Promise<void>) => Promise<void> }) {
  const [ask, setAsk] = useState<"post" | "disconnect" | null>(null);
  const s = netState(n);
  const [cap, setCap] = useState(String(n.month?.cap ?? ""));
  const connect = () => act(`${n.key}-connect`, async () => {
    const { url } = await api<{ url: string }>(`/admin/social/${n.key}/connect`, { method: "POST" });
    window.location.assign(url);
  });
  return (
    <Card label={n.name}>
      <CardHead title={n.name} info={`Signs in as you with ${n.name}'s own page (scopes: ${n.scopes}); the server keeps the sign-in sealed and never shows it here.`} />
      <div className="k-stack" data-testid={`social-${n.key}`}>
        <p className="k-small"><Light state={s.state} word={s.word} /> {s.detail}</p>
        <CheckField label={`Post daily on ${n.name}, ${schedule}`} checked={n.enabled} disabled={!n.connected || busy !== null}
          onChange={(on) => { void act(`${n.key}-switch`, async () => { await api(`/admin/social/${n.key}`, { method: "PUT", body: { enabled: on } }); }); }} />
        <div className="k-row">
          <button type="button" className={`btn sm${n.connected ? " outline" : ""}`} disabled={!n.configured || busy !== null} onClick={() => { void connect(); }}>
            {n.connected ? `Reconnect ${n.name}` : `Connect ${n.name}`}</button>
          <button type="button" className="btn outline sm" disabled={!n.connected || !n.next || busy !== null} onClick={() => setAsk("post")}>Post now</button>
          {n.connected && <button type="button" className="btn quiet sm" disabled={busy !== null} onClick={() => setAsk("disconnect")}>Disconnect</button>}
        </div>
        {n.month && (
          <div className="k-stack k-tight" data-testid={`social-month-${n.key}`}>
            <p className="k-small">This month: <b>{n.month.posts}</b> post{n.month.posts === 1 ? "" : "s"}{n.month.replies ? ` and ${n.month.replies} repl${n.month.replies === 1 ? "y" : "ies"}` : ""},
              about <b>${n.month.cost_usd.toFixed(2)}</b>{n.month.usd_inr ? ` (₹${Math.round(n.month.cost_usd * n.month.usd_inr).toLocaleString("en-IN")})` : ""} at
              ${n.month.rates.link_post.toFixed(2)} a post with a link and ${n.month.rates.reply.toFixed(2)} a reply. Cap: {n.month.cap} a month.</p>
            {n.month.paused && <p className="k-small k-down" role="status">{n.month.paused}</p>}
            <div className="k-row">
              <label className="k-small">Posts a month before X pauses <input className="k-input sm adm-cap" type="number" min={0} max={200} value={cap} onChange={(e) => setCap(e.target.value)} /></label>
              <button type="button" className="btn outline sm" disabled={busy !== null || !/^\d+$/.test(cap) || Number(cap) === n.month.cap}
                onClick={() => { void act(`${n.key}-cap`, async () => { await api(`/admin/social/${n.key}`, { method: "PUT", body: { cap: Number(cap) } }); }); }}>Save cap</button>
            </div>
          </div>
        )}
        <p className="k-note k-muted">Address to register in the {n.name} app: <span className="adm-mono adm-break">{n.callback}</span></p>
        <div className="k-stack k-tight" data-testid={`social-next-${n.key}`}>
          <b className="k-small">Next post{n.next ? `: ${n.next.theme}, ${n.enabled ? n.next.at : "when switched on"}` : ""}</b>
          {n.next ? n.next.parts.map((p, i) => (
            <div key={i} className="adm-post">
              <p className="adm-post-t">{p}</p>
              <span className="k-note k-muted">{n.next!.parts.length > 1 ? `Post ${i + 1} of ${n.next!.parts.length} · ` : ""}{p.length} of {LIMIT[n.key]} characters</span>
            </div>
          )) : <p className="k-small k-muted">{n.next_note ?? "No post to preview."}</p>}
        </div>
      </div>
      {ask === "post" && <ConfirmDialog title={`Post to ${n.name} now?`} confirmLabel={`Post to ${n.name}`} danger={false} busy={busy !== null}
        onClose={() => setAsk(null)} onConfirm={() => { setAsk(null); void act(`${n.key}-post`, async () => { await api(`/admin/social/${n.key}/post-now`, { method: "POST" }); }); }}>
        The next post ({n.next?.theme}) goes to {n.account ?? "your account"} now, for real. The daily post still goes at its time.</ConfirmDialog>}
      {ask === "disconnect" && <ConfirmDialog title={`Disconnect ${n.name}?`} confirmLabel="Disconnect" busy={busy !== null}
        onClose={() => setAsk(null)} onConfirm={() => { setAsk(null); void act(`${n.key}-off`, async () => { await api(`/admin/social/${n.key}/disconnect`, { method: "POST" }); }); }}>
        StratLab forgets the sign-in and stops posting to {n.name}. To remove its access fully, remove the app in {n.name}'s own settings too.</ConfirmDialog>}
    </Card>
  );
}

export function SocialSection() {
  const { fail, notify } = useApp();
  const { reload } = useAdmin();
  const [v, setV] = useState<SocialState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [params, setParams] = useSearchParams();
  const load = useCallback(async () => { try { setV(await api<SocialState>("/admin/social")); } catch (e) { fail(e); } }, [fail]);
  useEffect(() => { void load(); }, [load]);
  // back from X's or LinkedIn's sign-in page: say how it went, once
  useEffect(() => {
    const net = params.get("social"), result = params.get("result");
    if (!net || !result) return;
    notify(`${net === "x" ? "X" : "LinkedIn"} ${RESULT[result] ?? "sign-in finished."}`);
    setParams((p) => { p.delete("social"); p.delete("result"); return p; }, { replace: true });
  }, [params, setParams, notify]);
  const act = useCallback(async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    try { await fn(); } catch (e) { fail(e); } finally { setBusy(null); await load(); void reload(); }
  }, [fail, load, reload]);
  const cols: Column<SocialPost>[] = [
    { key: "at", header: "When", sortValue: (r) => r.at, cell: (r) => fmtDateTime(r.at, { zone: true, tz: IST }) },
    { key: "net", header: "Network", cell: (r) => `${r.name}${r.kind === "manual" ? " (test)" : ""}` },
    { key: "theme", header: "Theme", rowHeader: true, wrap: true, lead: true, cell: (r) => (
      <span className="k-stack k-tight"><span>{r.theme ?? "–"}{r.region ? <span className="k-note k-muted"> · {r.region === "IN" ? "India" : "US"}</span> : null}</span>
        {r.text && <span className="k-note k-muted adm-break">{r.text.length > 140 ? `${r.text.slice(0, 139)}…` : r.text}</span>}</span>) },
    { key: "status", header: "Status", sortValue: (r) => STATUS[r.status]?.word ?? r.status, wrap: true, cell: (r) => (
      <span className="k-stack k-tight"><Light state={STATUS[r.status]?.state ?? "warn"} word={STATUS[r.status]?.word ?? r.status} />
        {r.error && <span className="k-note adm-break">{r.error}{r.attempts > 1 ? ` (tried ${r.attempts} times)` : ""}</span>}</span>) },
    { key: "link", header: "Link", sortable: false, cell: (r) => r.url ? <a className="link" href={safeHref(r.url)} target="_blank" rel="noopener noreferrer">Open post ↗</a>
      : r.link ? <a className="link" href={safeHref(r.link)} target="_blank" rel="noopener noreferrer">Theme page ↗</a> : "–" },
  ];
  if (!v) return <Card label="Social"><Skeleton label="Loading Social" lines={4} /></Card>;
  return (
    <div className="k-stack">
      {!v.vault_ready && <p className="k-small k-down" role="alert">CONNECT_SECRET_KEY isn't set on the server, so no sign-in can be stored: add it in Railway → Variables first.</p>}
      {v.offline && <p className="k-small k-muted" role="status">This server is a test copy: it never calls X or LinkedIn.</p>}
      <div className="adm-social">
        {v.networks.map((n) => <NetCard key={n.key} n={n} schedule={v.schedule} busy={busy} act={act} />)}
      </div>
      <Card label="Last posts">
        <CardHead title={`Last posts (${v.posts.length})`} info="The last 20 posts, newest first: daily ones and tests sent with Post now. A post the network refused is tried once more 15 minutes later; one cut off without an answer is never sent again by itself, as it may have gone out." />
        {v.posts.length ? <DataTable label="Last posts" rows={v.posts} rowKey={(r) => r.id} columns={cols} stack />
          : <EmptyState title="Nothing posted yet">Posts show here once a network is connected and switched on, or after Post now.</EmptyState>}
      </Card>
    </div>
  );
}
