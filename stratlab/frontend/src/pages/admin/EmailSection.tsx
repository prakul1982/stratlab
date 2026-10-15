import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { Badge, Card, CardHead, EmptyState, ErrorState, Seg, Skeleton } from "../../components/kit";
import { useAdmin } from "./AdminContext";
import { sendErrorLine, sentLine } from "./testSend";

type Item = { kind: string; name: string; group: string; subject?: string; unsubscribe?: boolean; transactional?: boolean; error?: string };
type Full = { kind: string; name: string; group: string; subject: string; html: string; text: string; unsubscribe: boolean; transactional: boolean };
type View = "desktop" | "phone" | "text";
const VIEWS = [{ value: "desktop", label: "Desktop" }, { value: "phone", label: "Phone" }, { value: "text", label: "Text" }];

function List({ items }: { items: Item[] }) {
  const groups = useMemo(() => {
    const m = new Map<string, Item[]>();
    for (const i of items) m.set(i.group, [...(m.get(i.group) ?? []), i]);
    return [...m.entries()];
  }, [items]);
  return (
    <Card label="Emails">
      <CardHead title={`${items.length} emails`} info="Each sample goes through the same builder the real email uses. The market briefs show the newest issue actually built (its real figures); the other emails use made-up details. Nothing is sent." />
      <div className="adm-mail-list" role="list" aria-label="Emails">
        {groups.map(([group, rows]) => (
          <div key={group}>
            <div className="adm-mail-group k-eyebrow">{group}</div>
            {rows.map((r) => (
              <div key={r.kind} role="listitem">
                <Link className="adm-mail-row" to={`/admin/emails/${r.kind}`}>
                  <span><b>{r.name}</b><span className="k-note k-muted">{r.error ? `Couldn't build this sample: ${r.error}` : r.subject}</span></span>
                  <span className="k-row">
                    {r.transactional && <Badge dot={false}>Always sent</Badge>}
                    {r.unsubscribe && <Badge dot={false}>One-click unsubscribe</Badge>}
                  </span>
                </Link>
              </div>
            ))}
          </div>
        ))}
      </div>
    </Card>
  );
}

function One({ kind }: { kind: string }) {
  const { fail, notify } = useApp();
  const { ov } = useAdmin();
  const [mail, setMail] = useState<Full | null>(null);
  const [bad, setBad] = useState(false);
  const [view, setView] = useState<View>("desktop");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const sending = useRef(false);
  useEffect(() => {
    setMail(null); setBad(false); setResult(null);
    api<Full>(`/admin/email-previews/${encodeURIComponent(kind)}`).then(setMail).catch((e) => { setBad(true); fail(e); });
  }, [kind, fail]);
  const sendable = kind.startsWith("lifecycle_") && !!ov?.server.admin_alerts?.email_ready;
  // every press gets an answer that stays under the button until the next one (R23-009), and a second press while the
  // first is still sending does nothing
  const test = async () => {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setResult(null);
    try {
      const r = await api<{ sent_to: string; subject: string }>(`/admin/lifecycle/${kind.replace("lifecycle_", "")}/test`, { method: "POST" });
      const line = sentLine(r.subject, r.sent_to, new Date());
      setResult({ ok: true, text: line });
      notify(line);
    } catch (e) {
      setResult({ ok: false, text: sendErrorLine(e, new Date()) });
      fail(e);
    } finally { sending.current = false; setBusy(false); }
  };
  if (bad) return <ErrorState title="Couldn't build this email" action={{ label: "All emails", to: "/admin/emails" }}>It may have been removed. Open the list to pick another.</ErrorState>;
  if (!mail) return <Card label="Email"><Skeleton label="Building the email" /></Card>;
  return (
    <Card label={mail.name}>
      <CardHead title={mail.name} actions={<>
        <Link className="btn quiet sm" to="/admin/emails">All emails</Link>
        {sendable && <button type="button" className="btn quiet sm" disabled={busy} aria-busy={busy} onClick={test}>{busy ? "Sending…" : "Send me a test"}</button>}
      </>} />
      {sendable && busy && <p className="k-small k-muted" role="status">Sending the test email…</p>}
      {sendable && !busy && result && <p className={`k-small${result.ok ? "" : " k-warn-text"}`} role={result.ok ? "status" : "alert"} data-testid="test-send-result">{result.text}</p>}
      <p className="k-small"><b>Subject:</b> {mail.subject}</p>
      <div className="k-toolbar">
        <Seg label="Email view" options={VIEWS} value={view} onChange={(v) => setView(v as View)} />
        <span className="k-row">
          {mail.transactional && <Badge dot={false}>Always sent</Badge>}
          {mail.unsubscribe && <Badge dot={false}>One-click unsubscribe</Badge>}
        </span>
      </div>
      {view === "text"
        ? <pre className="adm-mail-text" aria-label="Plain text of the email">{mail.text}</pre>
        : (
          <div className="adm-mail-stage">
            {/* srcdoc with an empty sandbox: the email runs no scripts, opens no links of its own and is cut off from this page */}
            <iframe className={`adm-mail-frame ${view}`} title={`Preview: ${mail.subject}`} sandbox="" srcDoc={mail.html} />
          </div>
        )}
    </Card>
  );
}

/** Admin → Email previews: the 25 kinds of email as a list; open one to see it at a desktop or a phone width, or as text. */
export function EmailSection() {
  const { fail } = useApp();
  const { kind } = useParams();
  const [items, setItems] = useState<Item[] | null>(null);
  useEffect(() => { api<{ previews: Item[] }>("/admin/email-previews").then((x) => setItems(x.previews)).catch(fail); }, [fail]);
  if (kind) return <One kind={kind} />;
  if (!items) return <Card label="Emails"><Skeleton label="Building the sample emails" lines={6} /></Card>;
  if (!items.length) return <EmptyState title="No emails">There are no email types to show.</EmptyState>;
  return <List items={items} />;
}
