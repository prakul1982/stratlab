import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { download, shareLink, siteUrl } from "../lib/share";
import { renderCompanyCard, type CompanyCard } from "./companyCard";
import { Share } from "./Icons";
import { track } from "../lib/analytics";

const asDataUrl = (blob: Blob) => new Promise<string>((ok) => { const r = new FileReader(); r.onload = () => ok(String(r.result)); r.readAsDataURL(blob); });

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
      const out = await api<{ token: string }>(path, { method: "POST", body: { image: await asDataUrl(blob) } });
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

type Invites = { code: string; link: string; joined: number; months?: number; cap?: number; free_basic_until?: string | null; banked_days?: number };

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** Account → Invite friends: the user's own link, how many friends joined through it and the free months earned. */
export function InviteCard() {
  const { notify } = useApp();
  const [v, setV] = useState<Invites | null>(null);
  useEffect(() => {
    let live = true;
    api<Invites>("/me/referrals").then((x) => { if (live && x?.code) setV(x); }).catch(() => undefined);
    return () => { live = false; };
  }, []);
  if (!v) return null;
  const link = `${siteUrl()}/?ref=${v.code}`;
  const share = async () => {
    const r = await shareLink({ url: link, title: "StratLab", text: "I use StratLab to test trading ideas and read company facts. Try it free:" });
    if (r !== "cancelled") track("invite link shared", { channel: r });
    if (r === "copied") notify("Invite link copied.");
    else if (r === "shown") notify(`Your invite link: ${link}`);
  };
  return (
    <section className="card stack" style={{ gap: 12 }} id="invite">
      <div className="spread" style={{ gap: 12, flexWrap: "wrap" }}>
        <h2 className="h2">Invite friends</h2>
        <span className="pill" data-testid="friends-joined">{plural(v.joined, "friend", "friends")} joined · {plural(v.months ?? 0, "free month", "free months")} earned</span>
      </div>
      <p className="small muted" style={{ margin: 0 }} data-testid="invite-reward-line">When a friend joins through your link and uses StratLab on 3 different days in their first two weeks, you both get a month of Basic free (up to {v.cap ?? 12} months for you).</p>
      {(v.banked_days ?? 0) > 0 && <p className="small muted" style={{ margin: 0 }}>{v.banked_days} days of free Basic are kept for you: they start if your paid plan stops.</p>}
      <div className="row wrap" style={{ gap: 10 }}>
        <input className="input" readOnly value={link} aria-label="Your invite link" style={{ flex: "1 1 260px", minWidth: 0 }} onFocus={(e) => e.target.select()} />
        <button className="btn outline" onClick={share}><Share size={16} /> Share your link</button>
      </div>
    </section>
  );
}
