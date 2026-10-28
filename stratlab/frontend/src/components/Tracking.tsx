import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { askNow, CHOICE_KEY, clearChoice, consentWords, onChoice, readChoice, trackersFor, writeChoice, type Choice } from "../lib/ads";
import { doNotTrack } from "../lib/analytics";
import { flushSignup, loadPixel, onSignup, pixelPageView, startClarity, stopClarity } from "../lib/track";
import { CONFIG } from "./AdUnit";

/* The one question for Google ads, the Meta Pixel and Microsoft Clarity (ADS-1), and the loader for the last two. Mounted once, in
 * the public half and in the app. Nothing is asked, and nothing loads, unless an ad slot is set up or a pixel or Clarity ID is
 * set; no script comes before "Allow"; the private pages (money, tax, holdings, net worth, account, settings, admin, payment) are
 * never asked and load nothing, and Clarity stops there. */

/** The answer, following changes made on this page and in other tabs. */
export function useChoice(): Choice {
  const [choice, setChoice] = useState<Choice>(readChoice);
  useEffect(() => {
    const on = (e: StorageEvent) => { if (e.key === CHOICE_KEY) setChoice(readChoice()); };
    window.addEventListener("storage", on);
    const off = onChoice(() => setChoice(readChoice()));
    return () => { window.removeEventListener("storage", on); off(); };
  }, []);
  return choice;
}

export function Tracking() {
  const { pathname } = useLocation();
  const choice = useChoice();
  const want = trackersFor({ cfg: CONFIG, choice, path: pathname, dnt: doNotTrack() });
  useEffect(() => {
    if (want.pixel) { loadPixel(CONFIG.pixel); pixelPageView(pathname); flushSignup(); }
    if (want.clarity) startClarity(CONFIG.clarity); else stopClarity();
  }, [want.pixel, want.clarity, pathname]);
  // a sign-up that completes after the page has loaded
  useEffect(() => onSignup(() => { if (want.pixel) flushSignup(); }), [want.pixel]);
  if (!askNow({ cfg: CONFIG, choice, path: pathname })) return null;
  const { title, text } = consentWords(CONFIG);
  return (
    <div className="consent" role="dialog" aria-modal="false" aria-label={`${title} on StratLab`} data-testid="consent">
      <b className="consent-title">{title}</b>
      <p>{text} <Link className="link" to="/privacy">What this means</Link></p>
      <div className="consent-btns">
        <button type="button" className="btn sm" onClick={() => writeChoice("yes")}>Allow</button>
        <button type="button" className="btn quiet sm" onClick={() => writeChoice("no")}>No thanks</button>
      </div>
    </div>
  );
}

/** Privacy: the answer, and a way to change it. Taking a yes back reloads the page, so nothing already loaded keeps running. */
export function ChoiceControl() {
  const choice = useChoice();
  return (
    <p className="small" data-testid="ad-choice">
      <b>Your choice here:</b> {choice === "yes" ? "allowed" : choice === "no" ? "no thanks" : "not asked yet"}.{" "}
      {choice && <button type="button" className="btn quiet sm" onClick={() => { const was = choice; clearChoice(); if (was === "yes") location.reload(); }}>Change my choice</button>}
    </p>
  );
}
