import { useEffect, useId, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { askNow, CHOICE_KEY, clearChoice, consentWords, declineTrackers, onChoice, readAdsOnly, readChoice, readDeclined, trackersFor, writeChoice, type Choice } from "../lib/ads";
import { doNotTrack } from "../lib/analytics";
import { flushSignup, loadPixel, onSignup, pixelPageView, startClarity, stopClarity } from "../lib/track";
import { CONFIG } from "../lib/adsConfig";

/* The one question for Google ads, the Meta Pixel and Microsoft Clarity (ADS-1), and the loader for the last two. Mounted once, in
 * the public half and in the app. Nothing is asked, and nothing loads, unless an ad slot is set up or a pixel or Clarity ID is
 * set; no script comes before "Allow"; the private pages (money, tax, holdings, net worth, account, settings, admin, payment) are
 * never asked and load nothing, and Clarity stops there. */

/** The answer, following changes made on this page and in other tabs, and whether a yes was for Google ads alone (the question a page
 * the server draws asks, RC4-005). */
export function useAnswer(): { choice: Choice; adsOnly: boolean; declined: boolean } {
  const read = () => ({ choice: readChoice(), adsOnly: readAdsOnly(), declined: readDeclined() });
  const [answer, setAnswer] = useState(read);
  useEffect(() => {
    const on = (e: StorageEvent) => { if (e.key === CHOICE_KEY) setAnswer(read()); };
    window.addEventListener("storage", on);
    const off = onChoice(() => setAnswer(read()));
    return () => { window.removeEventListener("storage", on); off(); };
  }, []);
  return answer;
}

export function Tracking() {
  const { pathname } = useLocation();
  const { choice, adsOnly, declined } = useAnswer();
  const want = trackersFor({ cfg: CONFIG, choice, path: pathname, dnt: doNotTrack(), adsOnly });
  useEffect(() => {
    if (want.pixel) { loadPixel(CONFIG.pixel); pixelPageView(pathname); flushSignup(); }
    if (want.clarity) startClarity(CONFIG.clarity); else stopClarity();
  }, [want.pixel, want.clarity, pathname]);
  // a sign-up that completes after the page has loaded
  useEffect(() => onSignup(() => { if (want.pixel) flushSignup(); }), [want.pixel]);
  if (!askNow({ cfg: CONFIG, choice, path: pathname, adsOnly, declined, dnt: doNotTrack() })) return null;
  return <ConsentCard adsOnly={adsOnly} />;
}

/** The question itself. It stands over the bottom of the page, so while it is up the page keeps what has focus clear of it: a link or
 * button the keyboard reaches near the bottom scrolls up above the card, not under it (A11Y-2, WCAG 2.4.11). The page's own scroll
 * padding is the card's height, kept in step with it, and given back when the card goes. */
function ConsentCard({ adsOnly }: { adsOnly: boolean }) {
  const card = useRef<HTMLDivElement>(null);
  const text = useId();
  useEffect(() => {
    const el = card.current, root = document.documentElement;
    if (!el) return;
    // --consent-h: the page's own foot is padded by the card's height while it is up, so the end of a page is never under it (LIVE1B-050: the
    // refund policy's last lines and the landing page's example were cut off by it)
    const keep = () => { root.style.setProperty("scroll-padding-bottom", `${el.offsetHeight + 24}px`); root.style.setProperty("--consent-h", `${el.offsetHeight + 16}px`); };
    keep();
    const ro = typeof ResizeObserver === "function" ? new ResizeObserver(keep) : null;
    ro?.observe(el);
    return () => { ro?.disconnect(); root.style.removeProperty("scroll-padding-bottom"); root.style.removeProperty("--consent-h"); };
  }, []);
  const { title, text: words } = consentWords(CONFIG, adsOnly);
  return (
    <div ref={card} className="consent" role="dialog" aria-modal="false" aria-label={`${title} on StratLab`} aria-describedby={text} data-testid="consent">
      <b className="consent-title">{title}</b>
      <p id={text}>{words} <Link className="link" to="/privacy">What this means</Link></p>
      <div className="consent-btns">
        <button type="button" className="btn sm" onClick={() => writeChoice("yes")}>Allow</button>
        <button type="button" className="btn quiet sm" onClick={() => (adsOnly ? declineTrackers() : writeChoice("no"))}>No thanks</button>
      </div>
    </div>
  );
}

/** Privacy: the answer, and a way to change it. Taking a yes back reloads the page, so nothing already loaded keeps running. */
export function ChoiceControl() {
  const { choice, adsOnly } = useAnswer();
  return (
    <p className="small" data-testid="ad-choice">
      <b>Your choice here:</b> {choice === "yes" ? (adsOnly ? "allowed for Google ads only" : "allowed") : choice === "no" ? "no thanks" : "not asked yet"}.{" "}
      {choice && <button type="button" className="btn quiet sm" onClick={() => { const was = choice; clearChoice(); if (was === "yes") location.reload(); }}>Change my choice</button>}
    </p>
  );
}
