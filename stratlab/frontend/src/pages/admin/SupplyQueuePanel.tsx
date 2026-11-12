import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { fmtDate, safeHref } from "../../lib/format";
import type { QueueRow, SupplyAdmin } from "../../lib/companyLinks";
import { Card, CardHead, EmptyState, Select, Skeleton } from "../../components/kit";
import "../../components/companylinks.css";

/* Admin -> Data: customer and supplier names that fit more than one listed company (lane b2), modelled on the named holders'
 * spelling picker: pick the company the filing means, keep the name as filed (unlinked), or reject the link. A picked name is
 * remembered, so the same name is linked from then on. Also the job's switch state and this month's AI calls against the cap. */
function QueueItem({ r, done }: { r: QueueRow; done: (msg: string) => void }) {
  const [pick, setPick] = useState(r.candidates[0]?.symbol ?? "");
  const [busy, setBusy] = useState(false);
  const send = (body: Record<string, string>) => {
    setBusy(true);
    api<{ message: string }>(`/admin/supply-links/review/${encodeURIComponent(r.id)}`, { method: "POST", body })
      .then((x) => done(x.message), (e) => { setBusy(false); done(e instanceof Error ? e.message : "Couldn't save."); });
  };
  return (
    <li className="k-stack" data-queue={r.counterparty}>
      <span><b>{r.counterparty}</b> <span className="k-note">{r.direction === "customer" ? "named as a customer" : "named as a supplier"} by {r.stated_by} ({r.region}){r.said_on ? `, ${fmtDate(r.said_on)}` : ""}</span></span>
      <span className="k-small">“{r.quote}” <a className="link" href={safeHref(r.doc_url)} target="_blank" rel="noopener noreferrer">Filing ↗</a></span>
      <Select label={`Which company is “${r.counterparty}”?`} value={pick} onChange={setPick} small
        options={r.candidates.map((c) => ({ value: c.symbol, label: `${c.symbol}${c.name ? ` · ${c.name}` : ""}` }))} />
      <div className="k-row">
        <button className="btn sm" disabled={busy || !pick} onClick={() => send({ symbol: pick })}>Link to {pick || "…"}</button>
        <button className="btn quiet sm" disabled={busy} onClick={() => send({ action: "text" })}>Keep as filed</button>
        <button className="btn quiet sm" disabled={busy} onClick={() => send({ action: "reject" })}>Reject</button>
      </div>
    </li>
  );
}

export function SupplyQueuePanel() {
  const [v, setV] = useState<SupplyAdmin | null>(null);
  const [failed, setFailed] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const load = () => api<SupplyAdmin>("/admin/supply-links").then(setV, () => setFailed(true));
  useEffect(() => { load(); }, []);
  return (
    <Card label="Customer and supplier names">
      <CardHead title="Customer and supplier names" info="Names in filings that fit more than one listed company wait here; until then they show on the company page as filed, unlinked. The job itself is in the jobs list above (Customer and supplier map)." />
      {failed ? <p className="k-small k-down" role="alert">The queue couldn't be read. Reload the page.</p> : !v ? <Skeleton label="Loading the names queue" lines={3} /> : (
        <div className="k-stack">
          <p className="k-small">The nightly job is <b>{v.on ? "on" : "off"}</b>. AI calls this month: <b>{v.ai_used.toLocaleString("en-IN")}</b> of {v.ai_cap.toLocaleString("en-IN")}. Waiting: <b>{v.waiting}</b>.</p>
          {msg && <p className="k-small" role="status">{msg}</p>}
          {v.queue.length === 0 ? <EmptyState title="No names waiting">Every name found so far fits one company, or none.</EmptyState> : (
            <ul className="co-links-list">
              {v.queue.map((r) => <QueueItem key={r.id} r={r} done={(m) => { setMsg(m); load(); }} />)}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}
