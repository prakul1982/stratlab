import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { HELP } from "../lib/help";
import type { Cadence, NewsletterPrefs } from "../lib/news";
import { Info } from "./ui";

type Key = "market_in" | "market_us" | "my_stocks";
const ROWS: [Key, string][] = [["market_in", "Market brief: India"], ["market_us", "Market brief: US"], ["my_stocks", "My stocks"]];
const CHOICES: [Cadence, string][] = [["daily", "Daily"], ["weekly", "Weekly"], ["off", "Off"]];

/** Which plan a choice needs, or null when this plan allows it. */
function needs(p: NewsletterPrefs, key: Key, c: Cadence): string | null {
  if (c === "off") return null;
  if (key === "my_stocks") return p.allowed?.my_stocks === false ? "Pro" : null;
  return c === "daily" && p.allowed?.market_daily === false ? "Basic" : null;
}

/** Account → Newsletters: how often each brief is emailed, and where to. Saves on each change. */
export function NewslettersCard() {
  const { notify, fail } = useApp();
  const [prefs, setPrefs] = useState<NewsletterPrefs | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "missing" | "error">("loading");
  const [busy, setBusy] = useState<Key | "confirm" | null>(null);
  const loc = useLocation();
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    let live = true;
    api<NewsletterPrefs>("/me/newsletters")
      .then((p) => { if (!live) return; if (p && p.market_in) { setPrefs(p); setState("ready"); } else setState("missing"); })
      .catch((e: ApiError) => { if (live) setState(e.status === 404 ? "missing" : "error"); });
    return () => { live = false; };
  }, []);

  // the News page links here: bring the card into view once it has its final height
  useEffect(() => {
    if (loc.hash === "#newsletters" && state !== "loading") ref.current?.scrollIntoView({ block: "start" });
  }, [loc.hash, state]);

  const set = async (key: Key, c: Cadence) => {
    if (!prefs || prefs[key] === c) return;
    const before = prefs;
    setPrefs({ ...prefs, [key]: c });
    setBusy(key);
    try {
      const p = await api<NewsletterPrefs>("/me/newsletters", { method: "PUT", body: { [key]: c } });
      if (p && p.market_in) setPrefs(p);
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
    <section ref={ref} id="newsletters" className="card stack" style={{ gap: 12 }}>
      <div className="spread">
        <h2 className="h2 row" style={{ gap: 0 }}>Newsletters<Info>{HELP.newsletters}</Info></h2>
        <Link to="/news" className="btn quiet sm">Read past issues</Link>
      </div>
      {state === "loading" && <p className="small muted">Loading your newsletter settings…</p>}
      {state === "missing" && <p className="small muted">Newsletter settings aren't available yet. Check back soon.</p>}
      {state === "error" && <p className="small muted">Couldn't load your newsletter settings. Reload the page to try again.</p>}
      {state === "ready" && prefs && <>
        <div className="stack" style={{ gap: 0 }}>
          {ROWS.map(([key, title]) => (
            <div key={key} className="nl-row">
              <b style={{ fontSize: 15 }}>{title}</b>
              <div className="seg" role="radiogroup" aria-label={title}>
                {CHOICES.map(([c, name]) => {
                  const plan = needs(prefs, key, c);
                  return (
                    <button key={c} role="radio" aria-checked={prefs[key] === c} aria-pressed={prefs[key] === c}
                      disabled={!!plan || busy === key} title={plan ? `On the ${plan} plan` : undefined} onClick={() => set(key, c)}>
                      {name}{plan && <span className="badge next">{plan}</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
        {prefs.email ? (
          <div className="row wrap" style={{ gap: "8px 12px" }}>
            <span className="small" style={{ overflowWrap: "anywhere" }}>Sent to <b>{prefs.email}</b></span>
            {prefs.confirmed ? <span className="badge pass">Confirmed</span>
              : <button className="btn outline sm" disabled={busy === "confirm"} onClick={confirmEmail}>{busy === "confirm" ? "Sending…" : "Confirm this email"}</button>}
          </div>
        ) : <p className="small muted">There's no email on your account yet, so issues only show on the News page.</p>}
        {prefs.email && !prefs.confirmed && <p className="hint">Newsletters start once you've confirmed the email.</p>}
      </>}
    </section>
  );
}
