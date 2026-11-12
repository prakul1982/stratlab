import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { dateOnly } from "../lib/format";
import { shareCountLine, shareKindLabel, type ShareList, type ShareRow } from "../lib/researchShare";
import { researchShareApi } from "../lib/researchShareApi";
import { Badge, Card, CardHead, ConfirmDialog, DataTable, EmptyState, Skeleton, type Column } from "./kit";

/** Account: the person's share links to deep dives and themes (bet 3), each open or turned off, with this month's count against the
 *  plan's limit. Turning one off takes its public page down at once (the link then says it isn't available). */
export function ResearchSharesCard() {
  const { fail, notify } = useApp();
  const [data, setData] = useState<ShareList | null>(null);
  const [failed, setFailed] = useState(false);
  const [ask, setAsk] = useState<ShareRow | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => { setFailed(false); researchShareApi.list().then(setData).catch(() => setFailed(true)); };
  useEffect(load, []);
  const off = async () => {
    if (!ask) return;
    setBusy(true);
    try {
      await researchShareApi.off(ask.token);
      setData((d) => d && { ...d, links: d.links.map((x) => (x.token === ask.token ? { ...x, on: false } : x)) });
      notify("Link turned off. Anyone who opens it now sees that it isn't available.");
      setAsk(null);
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const columns: Column<ShareRow>[] = [
    { key: "t", header: "Shared", rowHeader: true, wrap: true, cell: (r) => (r.on ? <a className="link" href={r.url} target="_blank" rel="noopener noreferrer">{r.title}</a> : r.title) },
    { key: "k", header: "What", cell: (r) => shareKindLabel(r) },
    { key: "d", header: "Made", cell: (r) => dateOnly(r.made) },
    { key: "s", header: "Link", cell: (r) => (r.on
      ? <button type="button" className="btn quiet sm" onClick={() => setAsk(r)} aria-label={`Turn off the link to ${r.title}`}>Turn off</button>
      : <Badge tone="plain" dot={false}>Off</Badge>) },
  ];
  return (
    <Card id="shares" label="Shared research links">
      <CardHead title="Shared research links" info="A share link opens a dated snapshot of a deep dive or a theme for anyone, without signing in: its headline facts and the first sections, never your name, email, watchlist or holdings. Make one with Share link on a deep dive or a theme." />
      {failed && <p className="k-small">Your links couldn't be loaded. <button type="button" className="btn quiet sm" onClick={load}>Try again</button></p>}
      {!data && !failed && <Skeleton label="Loading your share links" lines={2} />}
      {data && <p className="k-small k-muted k-hint-line" data-testid="share-count">{shareCountLine(data.used, data.limit)}. <Link className="link" to="/plans">Plans</Link></p>}
      {data && data.links.length === 0 && <EmptyState title="No share links yet">Open a deep dive or a theme and press Share link to make a public snapshot of it.</EmptyState>}
      {data && data.links.length > 0 && <DataTable label="Your share links" columns={columns} rows={data.links} rowKey={(r) => r.token} />}
      {ask && <ConfirmDialog title="Turn this link off?" confirmLabel="Turn off" busy={busy} onConfirm={() => void off()} onClose={() => setAsk(null)}>
        Anyone who opens the link to {ask.title} will see that it isn't available. This can't be undone; you can share it again as a new link.</ConfirmDialog>}
    </Card>
  );
}
