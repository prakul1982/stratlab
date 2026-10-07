import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { HELP } from "../lib/help";
import type { Cadence, NewsletterPrefs } from "../lib/news";
import { track } from "../lib/analytics";
import { Badge, Card, CardHead, ErrorState, Notice, Seg, Skeleton } from "./kit";

type Key = "market_in" | "market_us" | "my_stocks";
const ROWS: [Key, string][] = [["market_in", "Market brief: India"], ["market_us", "Market brief: US"], ["my_stocks", "My stocks"]];
const CHOICES: [Cadence, string][] = [["daily", "Daily"], ["weekly", "Weekly"], ["off", "Off"]];

/** Which plan a choice needs, or null when this plan allows it. */
function needs(p: NewsletterPrefs, key: Key, c: Cadence): string | null {
  if (c === "off") return null;
  // weekly editions are for everyone; daily ones are Basic and up
  if (key === "my_stocks") return c === "daily" && p.allowed?.my_stocks_daily === false ? "Basic" : null;
  return c === "daily" && p.allowed?.market_daily === false ? "Basic" : null;
}

/** Settings → Notifications → Newsletters: how often each brief is emailed, and where to. Saves on each change. */
export function NewslettersCard() {
  const { notify, fail } = useApp();
  const [prefs, setPrefs] = useState<NewsletterPrefs | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "missing" | "error">("loading");
  const [busy, setBusy] = useState<Key | "confirm" | null>(null);
  const loc = useLocation();

  useEffect(() => {
    let live = true;
    api<NewsletterPrefs>("/me/newsletters")
      .then((p) => { if (!live) return; if (p && p.market_in) { setPrefs(p); setState("ready"); } else setState("missing"); })
      .catch((e: ApiError) => { if (live) setState(e.status === 404 ? "missing" : "error"); });
    return () => { live = false; };
  }, []);

  // the News page links here: bring the card into view once it has its final height
  useEffect(() => {
    if (loc.hash === "#newsletters" && state !== "loading") document.getElementById("newsletters")?.scrollIntoView({ block: "start" });
  }, [loc.hash, state]);

  const set = async (key: Key, c: Cadence) => {
    if (!prefs || prefs[key] === c) return;
    const before = prefs;
    setPrefs({ ...prefs, [key]: c });
    setBusy(key);
    try {
      const p = await api<NewsletterPrefs>("/me/newsletters", { method: "PUT", body: { [key]: c } });
      if (p && p.market_in) setPrefs(p);
      if (before[key] === "off" && c !== "off") track("newsletter subscribed", { kind: key, period: c });
      notify("Newsletter settings saved.");
    } catch (e) { setPrefs(before); fail(e); } finally { setBusy(null); }
  };
  const confirmEmail = async () => {
    setBusy("confirm");
    try {
      const r = await api<{ sent_to: string }>("/me/email/confirm", { method: "POST" });
      notify(`We've sent a link to ${r.sent_to || prefs?.email || "your email"}. Open it to confirm.`);
    } catch (e) { fail(e); } finally { setBusy(null); }
  };

  return (
    <Card id="newsletters" label="Newsletters">
      <CardHead title="Newsletters" info={HELP.newsletters} actions={<Link to="/news" className="btn quiet sm">Read past issues</Link>} />
      {state === "loading" && <Skeleton label="Loading your newsletter settings" lines={3} />}
      {state === "missing" && <p className="k-small k-muted">Newsletter settings aren't available yet. Check back soon.</p>}
      {state === "error" && <ErrorState title="Couldn't load your newsletter settings">Reload the page to try again.</ErrorState>}
      {state === "ready" && prefs && <>
        <div>
          {ROWS.map(([key, title]) => (
            <div key={key} className="k-line-row stack-narrow">
              <b>{title}</b>
              <Seg label={title} value={prefs[key]} onChange={(v) => void set(key, v as Cadence)}
                options={CHOICES.map(([c, name]) => {
                  const plan = needs(prefs, key, c);
                  return { value: c, label: plan ? `${name} · ${plan}` : name, disabled: !!plan || busy === key };
                })} />
            </div>
          ))}
        </div>
        {prefs.email ? (
          <div className="k-row">
            <span className="k-small">Sent to <b>{prefs.email}</b></span>
            {prefs.confirmed ? <Badge tone="ok">Confirmed</Badge>
              : <button type="button" className="btn outline sm" disabled={busy === "confirm"} onClick={() => void confirmEmail()}>{busy === "confirm" ? "Sending…" : "Confirm this email"}</button>}
          </div>
        ) : <p className="k-small k-muted">There's no email on your account yet, so issues only show on the News page.</p>}
        {prefs.email && !prefs.confirmed && <Notice>Newsletters start once you've confirmed the email.</Notice>}
      </>}
    </Card>
  );
}
