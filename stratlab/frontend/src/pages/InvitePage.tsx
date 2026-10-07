import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { shareLink, siteUrl } from "../lib/share";
import { track } from "../lib/analytics";
import { FRIEND_GETS, inviteRows, plural, youGet, type Invites } from "../lib/invite";
import { Share } from "../components/Icons";
import { Badge, Card, CardHead, ErrorState, Field, FormActions, FormGrid, PageHeader, Skeleton } from "../components/kit";

/** /invite: your own link, what a friend gets and what you get on your plan, and this year's count. */
export function InvitePage() {
  return (
    <div className="k-page">
      <PageHeader eyebrow="Invite friends" title="Invite friends" lede="Share your link. A friend who joins and uses StratLab gets a month of Basic free, and you earn free time too." />
      <InviteCard />
    </div>
  );
}

function InviteCard() {
  const { me, notify } = useApp();
  const [v, setV] = useState<Invites | null>(null);
  const [bad, setBad] = useState(false);
  useEffect(() => {
    let live = true;
    api<Invites>("/me/referrals").then((x) => { if (live && x?.code) setV(x); else if (live) setBad(true); }).catch(() => { if (live) setBad(true); });
    return () => { live = false; };
  }, []);
  if (!v && bad) return <Card label="Invite friends"><ErrorState title="Your invite link isn't available right now">Reload the page to try again.</ErrorState></Card>;
  if (!v || !me) return <Card label="Invite friends"><Skeleton label="Loading invite details" lines={3} /></Card>;
  const paid = me.paid_plan ?? me.plan;       // the plan they have; me.plan is Pro for everyone during the launch offer
  const link = `${siteUrl()}/?ref=${v.code}`;
  const share = async () => {
    const r = await shareLink({ url: link, title: "StratLab", text: "I use StratLab to test trading ideas and read company facts. Join with my link and use it on 3 different days in your first 2 weeks to get a month of Basic free:" });
    if (r !== "cancelled") track("invite link shared", { channel: r });
    if (r === "copied") notify("Invite link copied.");
    else if (r === "shown") notify(`Your invite link: ${link}`);
  };
  return (
    <Card id="invite" label="Invite friends">
      <CardHead title="Your invite link" actions={<span data-testid="friends-joined"><Badge dot={false}>{plural(v.joined, "friend")} joined · {plural(v.months ?? 0, "free month")} earned</Badge></span>} />
      <FormGrid label="Sharing" onSubmit={(e) => { e.preventDefault(); void share(); }}>
        <Field label="Your invite link" wide readOnly value={link} onFocus={(e) => e.target.select()} />
        <FormActions><button type="submit" className="btn outline"><Share size={16} /> Share your link</button></FormActions>
      </FormGrid>
      <div className="k-stack" data-testid="invite-reward-line">
        <p className="k-small"><b>What a friend gets.</b> {FRIEND_GETS}</p>
        <p className="k-small"><b>What you get.</b> {youGet(v, paid)}</p>
      </div>
      <div className="k-rows" data-testid="invite-status" aria-label="Your invites">
        {inviteRows(v, paid).map(([k, val]) => <div key={k}><span>{k}</span><b>{val}</b></div>)}
      </div>
    </Card>
  );
}
