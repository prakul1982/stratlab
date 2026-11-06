import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { AD_DESCRIPTION, AD_HEADLINE, AD_POINTS, AD_TITLE } from "../content/ad";
import { applySeo } from "../lib/seo";
import { absolute } from "../content/seo";
import { Google } from "../components/Icons";
import { Logo } from "../components/Logo";
import { track } from "../lib/analytics";
import { signIn, signInUnfinished } from "../lib/signin";
import { signInProblem } from "../lib/signinError";
import "./adlanding.css";

/** Where the visit says it came from, as analytics takes a word: the ad's utm_source, else "fbclid" for Meta's click id. */
function adSource(search: string): string {
  const q = new URLSearchParams(search);
  const s = (q.get("utm_source") ?? "").trim().toLowerCase();
  return /^[a-z][a-z0-9_-]{0,23}$/.test(s) ? s : q.has("fbclid") ? "fbclid" : "direct";
}

/** An event sent at once, by beacon, so it survives the page leaving for sign-in. Only when lib/analytics has the client running
 * (it starts it only where its rules allow: a key, no Do Not Track or Global Privacy Control): its storage key is there and the client,
 * a file already downloaded then, says it is loaded. False when not, and the caller uses the usual helper. */
async function sendNow(event: string, props: Record<string, string>): Promise<boolean> {
  try {
    if (!Object.keys(localStorage).some((k) => /^ph_.+_posthog$/.test(k))) return false;
    const { default: ph } = await import("posthog-js/dist/module.slim.no-external");
    if (!ph.__loaded) return false;
    ph.capture(event, props, { send_instantly: true, transport: "sendBeacon" });
    return true;
  } catch {
    return false;
  }
}

/* The ad landing (R15, owner 7 Nov: the social ad's visitors saw the full landing once and left, none read a second page). One phone
 * screen: what StratLab does in one line, one way in (Google sign-in, as on the landing page), three points, three small sample cards of the
 * app, and a link to the full landing. At /start, and on "/" for a visit from the ad (lib/deepLinks.ts isAdVisit); the address keeps the
 * ad's parameters. Its own file and stylesheet, loaded only for this view, so the landing page's download stays as it was (R5V-020). */
export function AdLanding() {
  const { pathname, search } = useLocation();
  const [error, setError] = useState<string | null>(() => signInProblem(location.search, location.hash, signInUnfinished()));
  const seen = useRef(false);
  const source = adSource(search);
  const kind = pathname.replace(/\/+$/, "") === "/start" ? "start" : "home";
  // its own title, description and canonical address (the home page) at /start, set after the visitor half's own (which knows only the
  // pages content/seo.ts lists); on "/" the home page's stay
  useEffect(() => {
    if (kind !== "start") return;
    document.title = AD_TITLE;
    applySeo({ description: AD_DESCRIPTION, canonical: absolute("/"), index: true }, AD_TITLE);
  }, [kind]);
  useEffect(() => {
    if (seen.current) return;
    seen.current = true;
    track("ad_landing_view", { kind, source });
  }, [kind, source]);
  const go = async () => {
    // the click leaves for Google at once, and an event waiting in the batch went with the page (none reached analytics): sent now,
    // on its own, when analytics is running; otherwise through the usual helper (which does nothing while analytics is off)
    if (!(await sendNow("ad_signup_click", { kind, source }))) track("ad_signup_click", { kind, source });
    void signIn(null).catch(() => setError("Couldn't start Google sign-in. Check your connection and try again."));
  };
  return (
    <div className="lp adl">
      <a className="skip-link sr-only" href="#main">Skip to main content</a>
      <header className="adl-top lp-wrap">
        <a href="/" className="brand" aria-label="StratLab home"><Logo size={34} /></a>
        <button type="button" className="btn outline sm" onClick={() => void go()}>Sign in</button>
      </header>
      <main id="main" tabIndex={-1} className="lp-wrap adl-main">
        <section className="adl-hero" aria-labelledby="ad-h1">
          <span className="eyebrow">Trade · Invest · Money</span>
          <h1 id="ad-h1" className="serif adl-h1">{AD_HEADLINE}</h1>
          <ul className="adl-points">
            {AD_POINTS.map((p) => <li key={p}>{p}</li>)}
          </ul>
          <div className="adl-go">
            <button type="button" className="btn lp-cta adl-cta" onClick={() => void go()}><Google />Try free with Google</button>
            <span className="small muted">Free to start · No card · No code</span>
          </div>
          {error && <p className="banner" role="alert">{error}</p>}
          <Link className="small adl-more" to="/">See everything StratLab does →</Link>
        </section>

        <section className="adl-shots" aria-label="What StratLab looks like: three samples">
          <figure className="lp-card adl-shot" data-space="trade">
            <figcaption className="eyebrow">Trade · sample result</figcaption>
            <p className="serif adl-quote">"Buy Bitcoin when RSI drops below 30, sell when it goes back above 55"</p>
            <b className="serif adl-verdict">Held up on unseen years.</b>
            <ul className="adl-rows">
              {([["Unseen data", "pass", "Passed"], ["Nearby settings", "pass", "Passed"], ["Bad-luck drawdown", "warn", "Warning"], ["Enough trades", "pass", "Passed"]] as const)
                .map(([t, s, l]) => <li key={t}><span>{t}</span><span className={`badge ${s}`}>{l}</span></li>)}
            </ul>
          </figure>
          <figure className="lp-card adl-shot" data-space="invest">
            <figcaption className="eyebrow">Invest · a made-up company</figcaption>
            <div className="adl-co"><b className="serif">Sample Motors</b><span className="adl-num">$183.20 <span className="k-delta up">▲ 1.33%</span></span></div>
            <ul className="adl-rows">
              <li><span>Sales, 3 years</span><span className="adl-num">68.2% a year</span></li>
              <li><span>Debt to equity</span><span className="adl-num">0.11</span></li>
              <li><span>Return on equity</span><span className="adl-num">41.9%</span></li>
              <li><span>Latest filing</span><span>Quarterly results</span></li>
            </ul>
          </figure>
          <figure className="lp-card adl-shot" data-space="money">
            <figcaption className="eyebrow">Money · sample figures</figcaption>
            <div className="adl-co"><b className="serif">Your holdings</b><span className="adl-num">₹5,08,043</span></div>
            <ul className="adl-rows">
              <li><span>Gain</span><span className="ad-num adl-up">+₹1,12,400</span></li>
              <li><span>XIRR</span><span className="ad-num adl-up">+14.2%</span></li>
              <li><span>Capital gains tax, this year</span><span className="adl-num">₹18,250</span></li>
              <li><span>ITR-ready export</span><span>Schedule CG</span></li>
            </ul>
          </figure>
        </section>
      </main>
      {/* the policies as plain links (not the shared footer: sharing it split it out of the landing page's own file, past its budget) */}
      <footer className="lp-wrap adl-foot">
        <nav className="k-row k-small legal-links" aria-label="Policies">
          {([["/terms", "Terms of service"], ["/privacy", "Privacy policy"], ["/refunds", "Cancellation and refunds"], ["/contact", "Contact us"]] as const)
            .map(([to, t]) => <Link key={to} className="muted" to={to}>{t}</Link>)}
        </nav>
      </footer>
    </div>
  );
}
