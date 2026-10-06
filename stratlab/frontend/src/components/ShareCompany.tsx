import { useEffect, useState } from "react";
import { api, dataUrl } from "../lib/api";
import { useApp } from "../lib/app";
import { download, shareLink, siteUrl } from "../lib/share";
import { renderCompanyCard, type CompanyCard } from "./companyCard";
import { Share } from "./Icons";
import { track } from "../lib/analytics";
import { Badge, Card, CardHead, Field, FormActions, ErrorState, FormGrid, Skeleton } from "./kit";

/** Share a company: draws its fact card, makes a public link that previews as the card (and opens the company's
 *  public page), then the phone's share sheet or, on a computer, the link copied with the image a click away. */
export function ShareCompanyButton({ region, symbol }: { region: "IN" | "US"; symbol: string }) {
  const { notify, fail } = useApp();
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      const path = `/cards/company/${region}/${encodeURIComponent(symbol)}`;
      const card = await api<CompanyCard>(path);
      const blob = await renderCompanyCard(card, "light");
      const out = await api<{ token: string }>(path, { method: "POST", body: { image: await dataUrl(blob) } });
      const url = `${siteUrl()}/c/${out.token}`;
      const file = new File([blob], `stratlab-${card.symbol.toLowerCase()}-facts.png`, { type: "image/png" });
      const save = { label: "Save the image", run: () => download(blob, file.name) };
      const r = await shareLink({ url, title: `${card.name} on StratLab`, text: `${card.name} (${card.symbol}): price, 1-year range and key facts.`, file });
      if (r !== "cancelled") track("card shared", { kind: "company", region, channel: r });
      if (r === "copied") notify("Link copied. It shows as this company's fact card on WhatsApp, X and LinkedIn.", save);
      else if (r === "shown") notify(`Your link: ${url}`, save);
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  return (
    <button className="btn quiet sm" onClick={run} disabled={busy} title="A card with this company's facts, and a link that previews as it">
      <Share size={16} /> {busy ? "Making the card…" : "Share"}
    </button>
  );
}

type Invites = { code: string; link: string; joined: number; months?: number; free_basic_until?: string | null; banked_days?: number;
  use_months?: number; use_cap?: number; paid_months?: number; paid_cap?: number; extras?: number; extra_pct?: number;
  waiting_to_subscribe?: number };

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** The invite rule in one place, for the invite page and anywhere else it's shown. */
const INVITE_LEAD = "Invite friends, both get a month of Basic.";
const inviteRule = (pct = 25) => "When a friend joins with your link and uses StratLab on 3 different days in their first 2 weeks, "
  + "they get a month of Basic free. You get a free month for each of your first 2 friends who do this each year, and for each of "
  + `your first 2 friends who subscribe. After that, every friend who subscribes gives you ${pct}% off a month (about a week extra).`;

/** The /invite page's card: the user's own link, how many friends joined through it, the free months earned and this
 *  year's rewards against their caps. */
export function InviteCard() {
  const { notify } = useApp();
  const [v, setV] = useState<Invites | null>(null);
  const [bad, setBad] = useState(false);
  useEffect(() => {
    let live = true;
    api<Invites>("/me/referrals").then((x) => { if (live && x?.code) setV(x); else if (live) setBad(true); }).catch(() => { if (live) setBad(true); });
    return () => { live = false; };
  }, []);
  if (!v && bad) return <Card label="Invite friends"><ErrorState title="Your invite link isn't available right now">Reload the page to try again.</ErrorState></Card>;
  if (!v) return <Card label="Invite friends"><Skeleton label="Loading invite details" lines={3} /></Card>;
  const link = `${siteUrl()}/?ref=${v.code}`;
  const share = async () => {
    const r = await shareLink({ url: link, title: "StratLab", text: "I use StratLab to test trading ideas and read company facts. Join with my link and use it on 3 different days in your first 2 weeks to get a month of Basic free:" });
    if (r !== "cancelled") track("invite link shared", { channel: r });
    if (r === "copied") notify("Invite link copied.");
    else if (r === "shown") notify(`Your invite link: ${link}`);
  };
  return (
    <Card id="invite" label="Invite friends">
      <CardHead title="Invite friends" actions={<span data-testid="friends-joined"><Badge dot={false}>{plural(v.joined, "friend", "friends")} joined · {plural(v.months ?? 0, "free month", "free months")} earned</Badge></span>} />
      <p className="k-small k-muted k-hint-line" data-testid="invite-reward-line"><strong>{INVITE_LEAD}</strong> {inviteRule(v.extra_pct)}</p>
      <div className="k-row">
        <span data-testid="invite-status"><Badge dot={false}>Use: {v.use_months ?? 0} of {v.use_cap ?? 2} · Subscribed: {v.paid_months ?? 0} of {v.paid_cap ?? 2} · Extra: {plural(v.extras ?? 0, "week", "weeks")}</Badge></span>
        {(v.waiting_to_subscribe ?? 0) > 0 && <span data-testid="invite-waiting"><Badge tone="warn" dot={false}>{plural(v.waiting_to_subscribe ?? 0, "friend", "friends")} waiting to subscribe</Badge></span>}
      </div>
      {(v.banked_days ?? 0) > 0 && <p className="k-small k-muted k-hint-line">{v.banked_days} days of free Basic are kept for you: they start if your paid plan stops.</p>}
      <FormGrid label="Sharing" onSubmit={(e) => { e.preventDefault(); void share(); }}>
        <Field label="Your invite link" wide readOnly value={link} onFocus={(e) => e.target.select()} />
        <FormActions><button type="submit" className="btn outline"><Share size={16} /> Share your link</button></FormActions>
      </FormGrid>
    </Card>
  );
}
