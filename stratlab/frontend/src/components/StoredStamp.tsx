import { useState } from "react";
import { writtenAt } from "../lib/format";
import { refreshesLeft, refreshNotOnPlan, REFRESH_ON_BASIC, resetsWord, usageChanged, usedWord, useUsage, type RefreshState, type UsageRow } from "../lib/usage";
import { DataTable, Skeleton, Working } from "./kit";

/* One way every stored shared read says how old it is and lets a person read it again (R19, owner 7 Nov: "tell the user exactly like
 * last update 6th, allowing them then to also refresh for fresh data"): the company AI read, the market's headline read, the head-to-head
 * comparison and a theme's read. A Refresh updates the read for everyone; within a few hours of the last one it is "already fresh", and
 * a person has a few a day (the note beside the button says how many are left). Never a raw error: a refresh that fails keeps the read
 * with its date. */

export type { RefreshState };
export const NO_REFRESH_LEFT = "No fresh AI reads left today, back at midnight IST";

/** "Last updated 6 Nov, 14:05 IST", the Refresh button and "4 left today", for a card's head. The count is the person's fresh AI reads,
 * the one Plans and Account state (LIVE7B-002); `counted` false: a read shared by everyone that no one's count holds (the market's
 * headlines read, LIVE7A-016), so no count is shown beside it. */
export function StoredStamp({ at, tz, busy, onRefresh, counted = true }: { at: number | null | undefined; tz?: string; busy: boolean; onRefresh: () => void; counted?: boolean }) {
  const { usage } = useUsage();
  const left = counted ? refreshesLeft(usage) : null;
  const none = left === 0;
  const off = refreshNotOnPlan(usage);           // FREE-TIER: none on the plan at all
  return (
    <span className="stored-stamp" data-testid="stored-stamp">
      {at ? <span className="k-note" data-testid="stored-at">Last updated {writtenAt(at, tz)}</span> : null}
      <button type="button" className="btn quiet sm" disabled={busy || none} title={off ? REFRESH_ON_BASIC : none ? NO_REFRESH_LEFT : undefined} onClick={onRefresh}>
        {busy ? "Refreshing…" : "Refresh"}
      </button>
      {(left != null || off) && <span className="k-note" data-testid="refresh-left">{off ? "On Basic" : none ? "None left today" : `${left} left today`}</span>}
    </span>
  );
}

/** Under the head: the loading bar while a Refresh is out, then one calm line saying what it did. */
export function StoredNote({ busy, state, at, tz, counted = true }: { busy: boolean; state: RefreshState | null; at: number | null | undefined; tz?: string; counted?: boolean }) {
  const { usage } = useUsage();
  if (busy) return <Working label="Refreshing for everyone…" />;
  const when = at ? writtenAt(at, tz) : "";
  const left = counted ? refreshesLeft(usage) : null;
  const msg = state === "fresh" ? `Updated ${when} – already fresh.`
    : state === "capped" ? `${refreshNotOnPlan(usage) ? REFRESH_ON_BASIC : NO_REFRESH_LEFT}. Showing the read from ${when}.`
    : state === "failed" ? `Couldn't refresh just now. Still showing the read from ${when}.`
    : state === "started" ? "Refreshing for everyone. It fills in here on its own."
    : state === "done" ? "Updated now, for everyone who opens it."
    : left === 0 ? `${refreshNotOnPlan(usage) ? REFRESH_ON_BASIC : NO_REFRESH_LEFT}.` : null;
  return msg ? <p className="k-note stored-note" role="status" data-testid="stored-note">{msg}</p> : null;
}

/** A Refresh's state and busy flag for one place: run() awaits the call, reads its "refresh_state" and updates the counts shown. */
export function useStoredRefresh() {
  const [busy, setBusy] = useState(false);
  const [state, setState] = useState<RefreshState | null>(null);
  const run = async <T extends { refresh_state?: RefreshState }>(call: () => Promise<T>): Promise<T | null> => {
    setBusy(true); setState(null);
    try {
      const out = await call();
      setState(out?.refresh_state ?? "done");
      return out;
    } catch {
      setState("failed");                 // the read on the page stays, with its date
      return null;
    } finally {
      setBusy(false);
      usageChanged();
    }
  };
  return { busy, state, run, clear: () => setState(null) };
}

/** Settings' "Your usage": every limit the app keeps for the person, from the same call as the Refresh notes. */
export function UsageTable() {
  const { usage, error } = useUsage();
  if (error) return <p className="k-small k-muted">Your usage can't be shown just now. Open this page again in a minute.</p>;
  if (!usage) return <Skeleton label="Reading your usage" lines={4} />;
  return (
    <DataTable label="Your usage" columns={[
      { key: "l", header: "Limit", rowHeader: true, wrap: true, cell: (r: UsageRow) => r.label },
      { key: "u", header: "Used", cell: (r) => usedWord(r) },
      { key: "left", header: "Left", numeric: true, cell: (r) => (r.left == null ? "–" : String(r.left)) },
      { key: "r", header: "Starts again", wrap: true, cell: (r) => resetsWord(r) },
    ]} rows={usage.rows} rowKey={(r) => r.key} stack />
  );
}
