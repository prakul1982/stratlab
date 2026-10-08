import { useApp } from "../lib/app";
import { VIEW_AS_CHOICES, choiceToPlan, planToChoice, viewAsBanner } from "../lib/viewAs";
import { Card, CardHead, Notice, Seg } from "./kit";

/** On every page while the site owner views the app as a plan: which plan, that the real one is unchanged, and the way
 * back. Read from the server's answer (me.view_as), so it never shows for anyone else. */
export function ViewAsBanner() {
  const { viewAs, setViewAs } = useApp();
  if (!viewAs) return null;
  return (
    <Notice tone="warn" role="status" className="k-viewas-banner" label="Viewing as another plan"
      action={{ label: "Turn off", onClick: () => { void setViewAs(null); } }}>
      {viewAsBanner(viewAs)}
    </Notice>
  );
}

/** Admin's card for "View as": Free, Basic, Pro or Off. Choosing one reloads the app as that plan, so plan locks, upgrade
 * prompts and monthly limits can be reviewed on the live site. Billing, the stored plan and Admin itself are unchanged. */
export function ViewAsCard() {
  const { viewAs, setViewAs } = useApp();
  return (
    <Card label="View as a plan">
      <CardHead title="View as a plan"
        info="See the whole app as a Free, Basic or Pro user does: their locks, upgrade prompts and monthly limits, with the launch offer left out. Only you see it. Your real plan, billing and Admin are unchanged, and it stays on until you turn it off." />
      <Seg label="View as" value={planToChoice(viewAs)} options={VIEW_AS_CHOICES} onChange={(v) => { void setViewAs(choiceToPlan(v)); }} />
    </Card>
  );
}
