import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { Card, CardHead, FigureTable, Skeleton } from "../../components/kit";

export type IpoQueue = { scheduled: number; cap: number; asked: number; waiting: number; days: number; to_read: number; per_pass: number };

const n = (x: number) => x.toLocaleString("en-IN");
const plural = (x: number, one: string, many: string) => `${n(x)} ${x === 1 ? one : many}`;

/** Admin → Data: the offer documents' queue (SECMEM 4, owner's item 40c). Today's AI summaries (the catch-up's against its
 * daily cap, and the ones people asked for, which are never held), the documents waiting for a summary with the days they
 * take at the cap, and the documents still to read. Was one sentence inside the IPO job's log, out of sight. */
export function IpoQueuePanel() {
  const [q, setQ] = useState<IpoQueue | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => { api<IpoQueue>("/admin/ipos/queue").then(setQ, () => setFailed(true)); }, []);
  return (
    <Card label="IPO offer documents">
      <CardHead title="IPO offer documents" info="Offer documents are read and summarised a few at a time between the IPO reads. A person opening an IPO always gets its summary on the spot; the daily cap holds only the background catch-up." />
      {failed ? <p className="k-small k-down" role="alert">The queue couldn't be read. Reload the page.</p> : !q ? <Skeleton label="Loading the IPO queue" lines={3} /> : (
        <FigureTable label="IPO offer documents: today and the backlog" header="Queue" valueHeader="Now" noteHeader="What it counts" rows={[
          { key: "today", label: "Summaries today, catch-up", value: `${n(q.scheduled)} of ${n(q.cap)}`, note: "The background catch-up, against its daily cap" },
          { key: "asked", label: "Summaries today, asked for", value: n(q.asked), note: "Written when someone opened an IPO; never capped" },
          { key: "wait", label: "Waiting for a summary", value: n(q.waiting),
            note: q.waiting ? `About ${plural(q.days, "day", "days")} at ${n(q.cap)} a day` : "None waiting" },
          { key: "read", label: "Still to read", value: n(q.to_read),
            note: q.to_read ? `Never read, or read by an older reader; ${q.per_pass} at a time between the IPO reads, not capped` : "Every document is read" },
        ]} />
      )}
    </Card>
  );
}
