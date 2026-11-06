import { zerodhaLine } from "../lib/zerodha";
import { brokerBadge, brokerLine, type BrokerStatus } from "../lib/brokers";
import { BrokerGuide } from "./BrokerGuide";
import { GUIDE_BROKERS } from "../lib/brokerGuide";
import { useCallback, useEffect, useState } from "react";
import { api, dataUrl } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, dateOnly } from "../lib/format";
import { Badge, Card, CardHead, CheckField, ConfirmDialog, DataTable, DateField, Disclosure, Field, FormActions, FormGrid, Notice, Skeleton, UploadButton, UploadProblem, useUploadProblem, Working, type Column } from "./kit";

/* Settings -> Connected accounts, the "connect once" cards: the statement inbox, the broker logins (Zerodha, Upstox, Dhan),
 * Interactive Brokers, and the EPF, NPS and
 * AIS uploads. Every figure on them is a fact about the connection (a date, a count, a status); passwords and tokens are typed
 * in and never shown again. */

type Last = { at: string; status: string; kind: string | null; via: string; detail: string };
type Conn = {
  storage_ready: boolean;
  inbox: { ready: boolean; address: string | null; has_password: boolean; last: Last | null; forwarding_code: { code: string; at: string } | null; created_at: string | null };
  kite: { configured?: boolean; available: boolean; connected: boolean; live: boolean; expired: boolean; refreshed_at: string | null; refreshed_label: string | null; count: number | null; detail: string | null; ends_at?: string | null };
  /** Upstox and Dhan, the same shape as Zerodha's */
  brokers?: (BrokerStatus & { refreshed_at: string | null; account: string | null })[];
  ibkr: { connected: boolean; synced_at: string | null; status: string | null; detail: string | null; positions: number | null; trades: number | null; expires: string | null };
  docs: Record<"epf" | "nps" | "ais", Record<string, unknown> | null>;
};

const WHAT: Record<string, string> = {
  ok: "Read and saved", wrong_password: "Couldn't open it: check your statement password", no_password: "It is locked: set your statement password",
  not_a_statement: "That PDF isn't a statement", summary_only: "That was the summary statement: ask for the detailed one", unreadable: "Couldn't be read",
  too_big: "The PDF was too large", no_pdf: "An email came with no PDF attached", empty: "No holdings were found in it", unknown: "Account not found",
};
const MAX_MB = 5;
/** "1 holding", "2 holdings", "0 holdings": a count with its word in the singular only for one (19.jpg: "Read 1 holdings.") */
const count = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** The shared copy of what the server knows, reloaded after every action. */
function useConnect() {
  const { fail } = useApp();
  const [c, setC] = useState<Conn | null | undefined>(undefined);
  const load = useCallback(() => { api<Conn>("/connect").then(setC).catch((e) => { setC(null); fail(e); }); }, [fail]);
  useEffect(() => {
    // back from Zerodha with a login to confirm: the confirm answers with the connections, so a load started alongside it
    // can't land after it with a half-done view (connected, holdings not read yet)
    const q = new URLSearchParams(window.location.search);
    if (!(q.get("kite") === "confirm" && q.get("ks") && q.get("kc")) && !(q.get("b") === "confirm" && q.get("broker") && q.get("bs") && q.get("bc"))) load();
  }, [load]);
  return { c, set: setC, load };
}

export function ConnectCards() {
  const { c, set, load } = useConnect();
  const { notify } = useApp();
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const k = q.get("kite");
    if (!k) return;
    const [ks, kc] = [q.get("ks"), q.get("kc")];
    for (const name of ["kite", "ks", "kc"]) q.delete(name);
    window.history.replaceState(null, "", window.location.pathname + (q.toString() ? `?${q}` : "") + window.location.hash);
    const say = (r: string) => notify(r === "ok" ? "Zerodha is connected and your holdings are read." : r === "cancelled" ? "The Zerodha login was cancelled." : "The Zerodha login didn't work. Try again.");
    if (k !== "confirm") { say(k); return; }
    // back from Zerodha: the login is only attached to the account that is signed in here, and only if it started there
    if (!ks || !kc) { say("failed"); return; }
    api<{ connect: Conn }>("/connect/kite/confirm", { method: "POST", body: { state: ks, claim: kc } })
      .then((r) => { set(r.connect); say("ok"); }).catch(() => { say("failed"); load(); });
  }, [notify, set, load]);
  useEffect(() => {
    // back from Upstox or Dhan: the same as Zerodha's, with the broker named in the address
    const q = new URLSearchParams(window.location.search);
    const [key, b, bs, bc] = [q.get("broker"), q.get("b"), q.get("bs"), q.get("bc")];
    if (!key || !b || !BROKER_NAMES[key]) return;
    for (const name of ["broker", "b", "bs", "bc"]) q.delete(name);
    window.history.replaceState(null, "", window.location.pathname + (q.toString() ? `?${q}` : "") + window.location.hash);
    const name = BROKER_NAMES[key];
    const say = (r: string) => notify(r === "ok" ? `${name} is connected and your holdings are read.` : r === "cancelled" ? `The ${name} login was cancelled.`
      // the broker itself said no (Dhan's own app and someone else's account): the other two ways still work
      : r === "refused" ? `${name} didn't allow this login yet. Upload your holdings file or forward your statement instead.` : `The ${name} login didn't work. Try again.`);
    if (b !== "confirm") { say(b); return; }
    if (!bs || !bc) { say("failed"); load(); return; }
    api<{ connect: Conn }>(`/connect/${key}/confirm`, { method: "POST", body: { ref: bs, claim: bc } })
      .then((r) => { set(r.connect); say("ok"); }).catch(() => { say("failed"); load(); });
  }, [notify, set, load]);
  if (c === undefined) return <Card label="Connecting your accounts"><Skeleton label="Loading your connections" /></Card>;
  if (c === null) return null;
  return (
    <>
      <BrokerGuide conn={c} where="settings" />
      <InboxCard c={c} set={set} load={load} />
      <BrokersCard c={c} set={set} />
      <IbkrCard c={c} set={set} />
      <DocsCard c={c} set={set} />
    </>
  );
}

type P = { c: Conn; set: (c: Conn) => void; load?: () => void };

/* ---------- the statement inbox ---------- */
function InboxCard({ c, set, load }: P) {
  const { fail, notify } = useApp();
  const [busy, setBusy] = useState(false);
  const [pw, setPw] = useState("");
  const [asking, setAsking] = useState(false);
  const [upPw, setUpPw] = useState("");
  const [remember, setRemember] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const i = c.inbox;

  const call = async (fn: () => Promise<Conn>, done?: string) => {
    setBusy(true);
    try { set(await fn()); if (done) notify(done); } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(i.address ?? ""); notify("Address copied."); } catch { notify("Select the address and copy it."); }
  };
  const { problem, clear: clearProblem, refused } = useUploadProblem();     // a wrong password or a file that isn't a statement stays beside the upload (RC6-010)
  const upload = async (files: FileList | null, reset: () => void) => {
    const f = files?.[0];
    reset();
    if (!f) return;
    if (f.size > MAX_MB * 1024 * 1024) { notify(`That file is larger than ${MAX_MB} MB. A statement is usually much smaller.`); return; }
    setBusy(true);
    setResult(null); clearProblem();
    try {
      const r = await api<{ detail: string; connect: Conn }>("/connect/statement", { method: "POST", body: { filename: f.name, data: await dataUrl(f), password: upPw, remember } });
      set(r.connect);
      setResult(r.detail || "Read and saved.");
    } catch (e) { if (!refused(e)) fail(e); } finally { setUpPw(""); setBusy(false); load?.(); }
  };

  return (
    <Card id="inbox" label="Statement inbox">
      <CardHead title="Statement inbox" info="Your statements from NSDL, CDSL, CAMS, KFintech and MF Central can reach StratLab by themselves (the depositories send one each month you trade, every six months otherwise). Set up one email filter, once, and your holdings and mutual funds update with each one. Each statement is read and then thrown away: only the holdings and transactions are kept."
        actions={<Badge tone={i.address ? "ok" : "plain"}>{!i.ready ? "Not set up yet" : i.address ? "On" : "Off"}</Badge>} />
      {!i.ready && <p className="k-small k-muted">The inbox isn't set up yet. You can still upload a statement below.</p>}
      {i.ready && !i.address && (
        <FormActions>
          <button type="button" className="btn" disabled={busy} onClick={() => void call(async () => (await api<Conn>("/connect/inbox", { method: "POST" })))}>Set up my inbox</button>
          <span className="k-small k-muted">Makes a private address for you. Nobody else can use it.</span>
        </FormActions>
      )}
      {i.address && <>
        <div className="k-field">
          <div className="k-label-row"><span className="k-lbl">Your address</span></div>
          <div className="k-row">
            <code className="k-address" data-testid="inbox-address">{i.address}</code>
            <button type="button" className="btn sm" onClick={() => void copy()}>Copy</button>
          </div>
        </div>
        {i.forwarding_code && <Notice role="status" label="Forwarding code">Gmail sent a confirmation code to this address: <b>{i.forwarding_code.code}</b>. Type it into Gmail's forwarding page to finish.</Notice>}
        <FormGrid onSubmit={(e) => { e.preventDefault(); if (pw.trim()) void call(async () => { const r = await api<Conn>("/connect/inbox/password", { method: "PUT", body: { password: pw } }); setPw(""); return r; }, "Password saved."); }}
          label="Statement password">
          <Field label="Your statement password" type="password" autoComplete="off" value={pw} maxLength={64} onChange={(e) => setPw(e.target.value)}
            placeholder={i.has_password ? "Saved. Type to replace it" : ""}
            info="Statements arrive locked. NSDL and CDSL use your PAN in capital letters. CAMS and KFintech use the password you chose when you asked for the statement, so choose the same one every time. It is kept encrypted, never shown again, and used only to open your statements." />
          <FormActions>
            <button type="submit" className="btn" disabled={busy || !pw.trim()}>{i.has_password ? "Change password" : "Set your statement password"}</button>
            {i.has_password && <button type="button" className="btn quiet" disabled={busy} onClick={() => void call(() => api<Conn>("/connect/inbox/password", { method: "DELETE" }), "Password removed.")}>Remove it</button>}
            {i.has_password ? <Badge tone="ok">Password saved</Badge> : <Badge tone="warn">No password yet</Badge>}
          </FormActions>
        </FormGrid>
        <div className="k-line-row" data-testid="inbox-last">
          <span className="k-line-text"><b>Last received</b>
            <span className="k-sub-line">{i.last ? `${dateOnly(i.last.at)} · ${i.last.via === "upload" ? "uploaded by hand" : "by email"}${i.last.detail ? ` · ${i.last.detail}` : ""}` : "Nothing yet. Statements arrive once your filter is set up."}</span></span>
          {i.last && <Badge tone={i.last.status === "ok" ? "ok" : "warn"}>{WHAT[i.last.status] ?? "Couldn't be read"}</Badge>}
        </div>
        <Disclosure summary="Set up the filter, once" testId="inbox-steps">
          <div className="k-stack">
            <p><b>Gmail</b></p>
            <ol className="k-steps">
              <li>Copy your address above. In Gmail, open Settings (the gear), then <i>See all settings</i>, then <i>Forwarding and POP/IMAP</i>.</li>
              <li>Press <i>Add a forwarding address</i> and paste it. Gmail sends a confirmation code to it. The code appears on this card; type it into Gmail and confirm. Don't turn on "Forward a copy of incoming mail".</li>
              <li>Open the <i>Filters and Blocked Addresses</i> tab and press <i>Create a new filter</i>. In the From box, type <code>nsdl.co.in OR cdslstatements.com OR camsonline.com OR kfintech.com OR mfcentral.com</code>. If a statement still gets missed, search your inbox for "Consolidated Account Statement" and use the From address you see on it.</li>
              <li>Press <i>Create filter</i>, tick <i>Forward it to</i>, choose your StratLab address, and press <i>Create filter</i>.</li>
            </ol>
            <p><b>Outlook</b></p>
            <ol className="k-steps">
              <li>Open Settings (the gear), then <i>Mail</i>, then <i>Rules</i>, then <i>Add new rule</i>.</li>
              <li>Name it "StratLab statements". For the condition, choose <i>Sender address includes</i> and add nsdl.co.in, cdslstatements.com, camsonline.com, kfintech.com and mfcentral.com.</li>
              <li>For the action, choose <i>Forward to</i> and paste your StratLab address. Save. Some work accounts don't allow forwarding outside the company; use a personal address for your statements then.</li>
            </ol>
            <p><b>Getting the statements</b></p>
            <p className="k-small k-muted">NSDL and CDSL email you a statement every month when you hold shares. For mutual funds, ask CAMS or KFintech once for a detailed statement with a monthly schedule, using the same password each time. Then it comes by itself.</p>
          </div>
        </Disclosure>
      </>}
      <div className="k-field">
        <div className="k-label-row"><span className="k-lbl">Upload a statement</span></div>
        <p className="k-small k-muted">If an email didn't arrive, upload the PDF here. It is read the same way.</p>
        <FormGrid label="Upload a statement">
          <div className="k-field-short"><Field label="Password" optional type="password" autoComplete="off" value={upPw} maxLength={64} onChange={(e) => setUpPw(e.target.value)}
            info="Needed when no statement password is saved above. It is used once to open the file." /></div>
          {/* on its own line under the box: squeezed into the grid's next 190px column its label ran over two lines (VR3-008) */}
          {!i.has_password && i.ready && <div className="k-field wide"><CheckField label="Save this password for next time" checked={remember} onChange={setRemember} /></div>}
          <FormActions><UploadButton label="Upload a statement" accept="application/pdf,.pdf" ariaLabel="Statement PDF" busy={busy} onFiles={(f, r) => void upload(f, r)} /></FormActions>
        </FormGrid>
        <UploadProblem problem={problem} />
        {result && <Notice role="status" label="Statement result">{result}</Notice>}
      </div>
      {i.address && <div><button type="button" className="btn quiet sm" onClick={() => setAsking(true)}>Turn off the inbox</button></div>}
      {asking && <ConfirmDialog title="Turn off the statement inbox?" confirmLabel="Turn it off" busy={busy} onClose={() => setAsking(false)}
        onConfirm={() => { void call(() => api<Conn>("/connect/inbox", { method: "DELETE" }), "The inbox is off and your password is deleted."); setAsking(false); }}>
        Your address stops working and your saved statement password is deleted. Holdings and funds already read stay.</ConfirmDialog>}
    </Card>
  );
}

/* ---------- the broker logins: Zerodha, Upstox, Dhan ---------- */
const BROKER_NAMES: Record<string, string> = { upstox: "Upstox", dhan: "Dhan" };

type BrokerRow = BrokerStatus & { id: string; path: string; line: string; lineId?: string };

/** One table, a row a broker, the same for each (LIVE1B-042 and TABLES EVERYWHERE): a broker that isn't open or set up is one short
 * row, not a card with a pill and one sentence. Zerodha keeps its own line (it ends its login at about 06:00 IST every day). */
function BrokersCard({ c, set }: P) {
  const { fail, notify } = useApp();
  const [busy, setBusy] = useState<{ key: string; what: string } | null>(null);
  const [asking, setAsking] = useState<BrokerRow | null>(null);
  const k = c.kite;
  const rows: BrokerRow[] = [
    { ...k, key: "kite", name: "Zerodha", id: "zerodha", path: "kite", line: k.available && k.connected ? zerodhaLine(k) : "", lineId: "kite-line" },
    ...(c.brokers ?? []).map((b) => ({ ...b, id: b.key, path: b.key, line: brokerLine(b), lineId: `${b.key}-line` })),
  ];
  // a broker whose live connection has been asked for but isn't there yet (Angel One) has its row too, saying so (LIVE4-015 partial:
  // the guide said "Not set up yet" while the table had no row for it)
  for (const g of GUIDE_BROKERS) {
    if (g.connect !== "none" || rows.some((r) => r.key === g.id || r.name === g.name)) continue;
    rows.push({ key: g.id, name: g.name, configured: false, available: false, connected: false, live: false, refreshed_label: null, count: null, detail: null,
      id: g.id, path: g.id, line: "No live connection yet: upload the holdings file in My Holdings, or email the monthly statement.", lineId: `${g.id}-line` });
  }
  const login = async (b: BrokerRow) => {
    setBusy({ key: b.key, what: `Opening the ${b.name} login` });
    try { const r = await api<{ url: string }>(`/connect/${b.path}/login`); window.location.href = r.url; } catch (e) { fail(e); setBusy(null); }
  };
  const refresh = async (b: BrokerRow) => {
    setBusy({ key: b.key, what: `Reading your ${b.name} holdings` });
    try {
      const r = await api<{ count: number; connect: Conn }>(`/connect/${b.path}/refresh`, { method: "POST" });
      set(r.connect);
      notify(`Read ${count(r.count, "holding")}.`);
      setBusy(null);
    } catch (e) {
      if ((e as { code?: string }).code === "login_needed") { await login(b); return; }
      fail(e); setBusy(null);
    }
  };
  const drop = async (b: BrokerRow) => {
    setBusy({ key: b.key, what: `Disconnecting ${b.name}` });
    try { set(await api<Conn>(`/connect/${b.path}`, { method: "DELETE" })); setAsking(null); notify(`${b.name} is disconnected and its stored login is deleted.`); }
    catch (e) { fail(e); } finally { setBusy(null); }
  };
  // only the rows whose badge says "Not open yet": a row not set up on the site says so itself (LIVE4-015: the note showed with no such row)
  const closed = rows.filter((b) => b.configured !== false && !b.available);
  const columns: Column<BrokerRow>[] = [
    { key: "name", header: "Broker", rowHeader: true, cell: (b) => <b>{b.name}</b> },
    { key: "status", header: "Status", wrap: true, cell: (b) => {
      const badge = brokerBadge(b);
      return (
        <span className="k-line-text">
          <Badge tone={badge.tone}>{badge.text}</Badge>
          {b.line && <span className="k-sub-line" data-testid={b.lineId}>{b.line}</span>}
          {b.available && b.detail && <span className="k-sub-line k-warn-text" role="status">{b.detail}</span>}
        </span>
      );
    } },
    { key: "act", header: "", action: true, cell: (b) => !b.available ? null : !b.connected
      ? <button type="button" className="btn" disabled={!!busy} onClick={() => void login(b)}>Connect {b.name}</button>
      : <span className="k-row">
          <button type="button" className="btn" disabled={!!busy} aria-label={b.live ? `Refresh ${b.name}` : undefined} onClick={() => void (b.live ? refresh(b) : login(b))}>{b.live ? "Refresh" : `Log in to ${b.name}`}</button>
          <button type="button" className="btn quiet" disabled={!!busy} aria-label={`Disconnect ${b.name}`} onClick={() => setAsking(b)}>Disconnect</button>
        </span> },
  ];
  return (
    <Card id="brokers" label="Brokers">
      <CardHead title="Brokers" info={<>Log in to your broker and your holdings are read into My Holdings. It is read-only: StratLab can't place orders or move money,
        and never sees your broker password. Each broker ends its login by itself (Zerodha at about 06:00 IST, Upstox at 03:30 IST;
        Dhan says when), so after that you log in once more. Refresh reads the holdings again while the login lasts.</>} />
      <DataTable label="Broker logins" columns={columns} rows={rows} rowKey={(b) => b.key} rowAttrs={(b) => ({ id: b.id, "data-testid": `broker-${b.key}` })} />
      {busy && <Working small label={`${busy.what}…`} />}
      {closed.length > 0 && <p className="k-small k-muted">{closed.length === rows.length ? "None of these is open for your account yet." : `A broker marked "Not open yet" isn't available for your account yet.`} Upload your broker's holdings file in My Holdings meanwhile.</p>}
      {asking && <ConfirmDialog title={`Disconnect ${asking.name}?`} confirmLabel="Disconnect" busy={!!busy} onClose={() => setAsking(null)} onConfirm={() => void drop(asking)}>
        Its stored login is deleted. Holdings already read stay in My Holdings. You can connect again any time.</ConfirmDialog>}
    </Card>
  );
}

/* ---------- Interactive Brokers ---------- */
function IbkrCard({ c, set }: P) {
  const { fail, notify } = useApp();
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState("");
  const [query, setQuery] = useState("");
  const [expires, setExpires] = useState("");
  const [asking, setAsking] = useState(false);
  const b = c.ibkr;
  const connect = async () => {
    setBusy(true);
    try {
      const r = await api<{ positions: number; trades_added: number; connect: Conn }>("/connect/ibkr", { method: "PUT", body: { token: token.trim(), query_id: query.trim(), expires: expires || null } });
      set(r.connect);
      setToken(""); setQuery(""); setExpires("");
      notify(`Connected. ${count(r.positions, "US position")} read, ${count(r.trades_added, "trade")} added to your journal.`);
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const refresh = async () => {
    setBusy(true);
    try { const r = await api<{ positions: number; trades_added: number; connect: Conn }>("/connect/ibkr/refresh", { method: "POST" }); set(r.connect); notify(`Read ${count(r.positions, "US position")}, ${count(r.trades_added, "new trade")}.`); }
    catch (e) { fail(e); } finally { setBusy(false); }
  };
  const drop = async () => {
    setBusy(true);
    try { set(await api<Conn>("/connect/ibkr", { method: "DELETE" })); notify("Interactive Brokers is disconnected and its token is deleted."); } catch (e) { fail(e); } finally { setBusy(false); setAsking(false); }
  };
  return (
    <Card id="ibkr" label="US stocks">
      <CardHead title="US stocks (Interactive Brokers)" info="Paste a read-only Flex token and query id from Interactive Brokers once. Every morning (India time) your US positions go to My Holdings and your closed trades to the trade journal. The token can't trade or move money."
        actions={<Badge tone={b.connected ? (b.status === "ok" ? "ok" : "warn") : "plain"}>{b.connected ? (b.status === "ok" ? "Connected" : "Needs attention") : "Not connected"}</Badge>} />
      {b.connected ? <>
        <p className="k-small" data-testid="ibkr-line">{b.synced_at ? `Read ${ago(b.synced_at)} · ${count(b.positions ?? 0, "US position")}, ${count(b.trades ?? 0, "new trade")}` : "Not read yet"}{b.expires ? ` · token ends ${dateOnly(b.expires)}` : ""}</p>
        {b.status && b.status !== "ok" && b.detail && <Notice tone="warn" role="status">{b.detail}</Notice>}
        <FormActions>
          <button type="button" className="btn" disabled={busy} onClick={() => void refresh()}>Refresh</button>
          <button type="button" className="btn quiet" disabled={busy} onClick={() => setAsking(true)}>Disconnect</button>
        </FormActions>
      </> : <FormGrid label="Connect Interactive Brokers" onSubmit={(e) => { e.preventDefault(); if (token.trim() && query.trim()) void connect(); }}>
        <Field label="Flex token" type="password" autoComplete="off" value={token} maxLength={200} onChange={(e) => setToken(e.target.value)} />
        <Field label="Query id" inputMode="numeric" value={query} maxLength={20} onChange={(e) => setQuery(e.target.value.replace(/\D/g, ""))} />
        <DateField label="Token ends on" optional value={expires} onChange={setExpires} info="The expiry date Interactive Brokers shows next to the token, so StratLab can tell you before it stops." />
        <FormActions><button type="submit" className="btn" disabled={busy || !token.trim() || !query.trim()}>{busy ? "Checking…" : "Connect"}</button></FormActions>
      </FormGrid>}
      <Disclosure summary="Where to find the token and query id">
        <ol className="k-steps">
          <li>Log in to Interactive Brokers' Client Portal and open <i>Performance &amp; Reports</i>, then <i>Flex Queries</i>.</li>
          <li>Create an <i>Activity Flex Query</i>. Tick the sections <i>Open Positions</i> and <i>Trades</i> with all their fields, choose the XML format and a period of the last 365 days, and save. The number beside the query is the query id.</li>
          <li>On the same page open <i>Flex Web Service Configuration</i>, turn it on, and generate a token that lasts as long as it allows (up to a year). Copy it here.</li>
        </ol>
      </Disclosure>
      {asking && <ConfirmDialog title="Disconnect Interactive Brokers?" confirmLabel="Disconnect" busy={busy} onClose={() => setAsking(false)} onConfirm={() => void drop()}>
        The stored token is deleted. Positions and trades already read stay.</ConfirmDialog>}
    </Card>
  );
}

/* ---------- EPF, NPS and AIS ---------- */
type Figure = { key: string; label: string; unit: string; value: string | number | null; found: boolean };
type Read = { kind: string; figures: Figure[]; lines: Record<string, unknown>[]; found: number };

const DOCS = {
  epf: { title: "EPF passbook", accept: "application/pdf,.pdf", help: "Download your passbook PDF from the member portal. The balance goes into Net worth." },
  nps: { title: "NPS statement", accept: "application/pdf,.pdf", help: "Upload the statement PDF from your NPS account. The Tier I and II values go into Net worth." },
  ais: { title: "AIS (annual information statement)", accept: "application/pdf,.pdf,application/json,.json", help: "Upload the JSON (best) or PDF from the income tax portal. Dividends and TDS can go to your tax tools." },
} as const;

function DocUpload({ kind, saved, set }: { kind: keyof typeof DOCS; saved: Record<string, unknown> | null; set: (c: Conn) => void }) {
  const { fail, notify } = useApp();
  const d = DOCS[kind];
  const [busy, setBusy] = useState(false);
  const [pw, setPw] = useState("");
  const [read, setRead] = useState<Read | null>(null);
  const [vals, setVals] = useState<Record<string, string>>({});
  const [tds, setTds] = useState(false);
  const { problem, clear: clearProblem, refused } = useUploadProblem();
  const pick = async (files: FileList | null, reset: () => void) => {
    const f = files?.[0];
    reset();
    if (!f) return;
    if (f.size > MAX_MB * 1024 * 1024) { notify(`That file is larger than ${MAX_MB} MB.`); return; }
    setBusy(true); clearProblem();
    try {
      const r = await api<Read>("/connect/docs/read", { method: "POST", body: { kind, filename: f.name, data: await dataUrl(f), password: pw } });
      setRead(r);
      setVals(Object.fromEntries(r.figures.map((x) => [x.key, x.value == null ? "" : String(x.value)])));
      notify(r.found ? "Check the figures below, then save them." : "Nothing could be read from that file. Type the figures in.");
    } catch (e) { if (!refused(e)) fail(e); } finally { setPw(""); setBusy(false); }
  };
  const save = async () => {
    if (!read) return;
    setBusy(true);
    try {
      const r = await api<{ detail: string; connect: Conn }>("/connect/docs/confirm", { method: "POST", body: { kind, figures: vals, apply_tds: tds, lines: read.lines } });
      set(r.connect);
      setRead(null);
      notify(r.detail);
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const summary = saved ? kind === "ais" ? `Saved for ${Object.keys(saved).sort().map((y) => `${y}-${String(Number(y) + 1).slice(2)}`).join(", ")}` : `Saved${saved.as_of ? ` as of ${dateOnly(String(saved.as_of))}` : ""}` : "Nothing saved yet";
  return (
    <div className="k-field wide" data-testid={`doc-${kind}`}>
      <div className="k-line-row">
        <span className="k-line-text"><b>{d.title}</b><span className="k-sub-line">{summary}</span></span>
        {!read && <UploadButton label="Upload" accept={d.accept} ariaLabel={`${d.title} file`} busy={busy} quiet onFiles={(f, r) => void pick(f, r)} />}
      </div>
      {!read && <>
        <p className="k-small k-muted">{d.help}</p>
        {/* LIVE1B-042: a password is a short box, not one as wide as the card */}
        {kind !== "ais" && <div className="k-field-short"><Field label="File password" optional type="password" autoComplete="off" value={pw} maxLength={64} onChange={(e) => setPw(e.target.value)} /></div>}
        <UploadProblem problem={problem} />
      </>}
      {read && (
        <FormGrid label={`${d.title} figures`} onSubmit={(e) => { e.preventDefault(); void save(); }}>
          {read.figures.map((f) => (
            <Field key={f.key} label={f.label} unit={f.unit === "₹" ? "₹" : undefined} type={f.unit === "date" ? "date" : "text"} inputMode={f.unit === "₹" || f.key === "fy" ? "decimal" : undefined}
              value={vals[f.key] ?? ""} onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })}
              info={f.found ? "Read from your file. Check it." : "Not found in the file. Type it in, or leave it empty."} />
          ))}
          {kind === "ais" && <CheckField label="Also set this TDS in my tax tools" checked={tds} onChange={setTds} />}
          {kind === "ais" && read.lines.length > 0 && <p className="k-small k-muted">{read.lines.length} dated dividend lines will be added to your dividends.</p>}
          <FormActions>
            <button type="submit" className="btn" disabled={busy}>Save these figures</button>
            <button type="button" className="btn quiet" disabled={busy} onClick={() => setRead(null)}>Cancel</button>
          </FormActions>
        </FormGrid>
      )}
    </div>
  );
}

function DocsCard({ c, set }: P) {
  return (
    <Card id="docs" label="EPF, NPS and AIS">
      <CardHead title="EPF, NPS and AIS" info="Figures that don't come in a statement email. StratLab looks in your file for them and shows what it found. You check the figures, and only then are they saved. The file itself is not kept." />
      <DocUpload kind="epf" saved={c.docs.epf} set={set} />
      <DocUpload kind="nps" saved={c.docs.nps} set={set} />
      <DocUpload kind="ais" saved={c.docs.ais} set={set} />
    </Card>
  );
}
