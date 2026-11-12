import { useEffect, useId, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { askNow, CHOICE_KEY, clearChoice, consentWords, declineTrackers, onChoice, readAdsOnly, readChoice, readDeclined, trackersFor, writeChoice, type Choice } from "../lib/ads";
import { doNotTrack } from "../lib/analytics";
import { flushSignup, loadPixel, onSignup, pixelPageView, startClarity, stopClarity } from "../lib/track";
import { CONFIG } from "../lib/adsConfig";
import { useGuideOpen } from "../lib/onboarding";

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
  // the welcome question and the tour come first: on a phone the two cards stood over each other and this one hid the
  // welcome choices (CI, 28 Oct), so the question waits until the guide is answered or closed
  const guiding = useGuideOpen();
  if (!askNow({ cfg: CONFIG, choice, path: pathname, adsOnly, declined, dnt: doNotTrack() })) return null;
  if (guiding) return null;
  return <ConsentCard adsOnly={adsOnly} />;
}

/** The question itself: a band in the page's own flow, above the page, so nothing is ever under it (LIVE7B-006). */
function ConsentCard({ adsOnly }: { adsOnly: boolean }) {
  const text = useId();
  const { title, text: words, short } = consentWords(CONFIG, adsOnly);
  // on a phone the slim bar shows the one-sentence question with "What this means" beside the answers (LIVE3-010); the card's
  // full wording is for wider screens (CSS shows one or the other)
  return (
    <div className="consent" role="dialog" aria-modal="false" aria-label={`${title} on StratLab`} aria-describedby={text} data-testid="consent">
      <b className="consent-title">{title}</b>
      <p id={text}><span className="consent-long">{words} <Link className="link" to="/privacy">What this means</Link></span><span className="consent-short">{short}</span></p>
      <div className="consent-btns">
        <Link className="link consent-more" to="/privacy">What this means</Link>
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
