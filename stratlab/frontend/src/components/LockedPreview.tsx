import type { ReactNode } from "react";
import { Card, CardHead } from "./kit";
import { PlanActions } from "./PlanInterest";

/** What a locked page holds, under its lock note, so the page isn't blank below the banner (DP1-019: Business updates, Named
 * holders, Chart replay and Forward test showed nothing but the lock). Plain facts about the page, no sample figures. */
export function LockedPreview({ title, points, free, actions = true }: {
  title: string; points: string[];
  /** where the free part of it is, when there is one */
  free?: ReactNode;
  /** offer the plans here too (off when the lock note above already does) */
  actions?: boolean;
}) {
  return (
    <Card label={`What ${title} shows`} testId="locked-preview">
      <CardHead title={`What ${title} shows`} level={2} />
      <ul className="k-list">{points.map((p) => <li key={p}>{p}</li>)}</ul>
      {free && <p className="k-note">{free}</p>}
      {actions && <div className="k-row"><PlanActions source="lock" /></div>}
    </Card>
  );
}
