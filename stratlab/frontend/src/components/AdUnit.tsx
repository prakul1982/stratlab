import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { CFG } from "../lib/config";
import { adMode, adsConfig, CHOICE_KEY, googleMessageShown, houseCard, readChoice, writeChoice, type AdSlotName, type Choice } from "../lib/ads";
import { signedInHere } from "../lib/signin";

/* One ad slot (ADS-1). What it shows is decided in lib/ads.ts (adMode): an ad, the question that comes before it, a StratLab
 * card, or nothing. Off by default: with no publisher ID nothing here loads Google's script or sets anything. Imports no account
 * code, so the public pages use it; the Free-account slot under an AI answer (components/AiAd.tsx) adds the plan. */

const CONFIG = adsConfig(import.meta.env as Record<string, unknown>, CFG as unknown as Record<string, unknown>);

/** Google's script, added once, and only after "Allow ads" (the question comes first). */
function addScript(client: string) {
  if (document.querySelector('script[src*="adsbygoogle.js"]')) return;
  const s = document.createElement("script");
  s.async = true;
  s.crossOrigin = "anonymous";
  s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${encodeURIComponent(client)}`;
  document.head.appendChild(s);
}

/** The labelled box Google fills. It holds its height from the start (no jump when the ad arrives) and is asked for only when
 * it is about to scroll into view. Its inside belongs to Google's script, so React draws nothing in it. */
function AdBox({ client, slot }: { client: string; slot: string }) {
  const box = useRef<HTMLDivElement>(null);
  const [gone, setGone] = useState(false);
  useEffect(() => {
    const area = box.current;
    if (!area) return;
    let started = false, mo: MutationObserver | null = null;
    const start = () => {
      if (started) return;
      started = true;
      addScript(client);
      const ins = document.createElement("ins");
      ins.className = "adsbygoogle";
      ins.style.display = "block";
      ins.setAttribute("data-ad-client", client);
      ins.setAttribute("data-ad-slot", slot);
      ins.setAttribute("data-ad-format", "auto");
      ins.setAttribute("data-full-width-responsive", "true");
      area.appendChild(ins);
      // an ad Google had none to fill: the label goes too, so no empty "Advertisement" is left on the page
      mo = new MutationObserver(() => { if (ins.getAttribute("data-ad-status") === "unfilled") setGone(true); });
      mo.observe(ins, { attributes: true, attributeFilter: ["data-ad-status"] });
      try { ((window as unknown as { adsbygoogle: unknown[] }).adsbygoogle ??= []).push({}); } catch { /* the script is blocked: the box stays empty */ }
    };
    // below the fold only: nothing is asked for until the box is near the screen
    const io = typeof IntersectionObserver === "function" ? new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { io?.disconnect(); start(); } }, { rootMargin: "300px 0px" }) : null;
    if (io) io.observe(area); else start();
    return () => { io?.disconnect(); mo?.disconnect(); };
  }, [client, slot]);
  if (gone) return null;
  return (
    <section className="ad" aria-label="Advertisement" data-testid="ad-slot">
      <p className="ad-label">Advertisement</p>
      <div className="ad-box" ref={box} />
    </section>
  );
}

/** The question before any ad: asked in the slot's own place, so it never covers the page. */
function AdAsk({ onChoose }: { onChoose: (c: "yes" | "no") => void }) {
  return (
    <section className="ad" aria-label="Ads on StratLab" data-testid="ad-consent">
      <p className="ad-label">Ads on StratLab</p>
      <div className="ad-ask">
        <p>StratLab shows Google ads on public pages and to Free accounts. They use cookies to choose and measure ads. Say no and no ad is loaded. Basic and Pro have no ads. <Link className="link" to="/privacy">What this means</Link></p>
        <div className="ad-btns">
          <button type="button" className="btn sm" onClick={() => onChoose("yes")}>Allow ads</button>
          <button type="button" className="btn quiet sm" onClick={() => onChoose("no")}>No thanks</button>
        </div>
      </div>
    </section>
  );
}

/** What holds a Free account's place when ads are off or declined: one of StratLab's own pages. Nothing is loaded or tracked. */
function House({ seed }: { seed: string }) {
  const c = houseCard(seed);
  return (
    <section className="ad ad-house" aria-label="From StratLab" data-testid="ad-house" data-house={c.id}>
      <p className="ad-label">From StratLab</p>
      <div className="ad-ask">
        <p><b>{c.title}</b></p>
        <p>{c.text}</p>
        <Link className="btn quiet sm" to={c.to}>{c.cta}</Link>
      </div>
    </section>
  );
}

export function AdUnit({ slot, plan = null, seed = "" }: { slot: AdSlotName; plan?: "free" | "basic" | "pro" | null; seed?: string }) {
  const { pathname } = useLocation();
  const [choice, setChoice] = useState<Choice>(readChoice);
  // an answer given in another tab of this browser applies here too
  useEffect(() => {
    const on = (e: StorageEvent) => { if (e.key === CHOICE_KEY) setChoice(readChoice()); };
    window.addEventListener("storage", on);
    return () => window.removeEventListener("storage", on);
  }, []);
  const mode = adMode({ slot, cfg: CONFIG, path: pathname, choice, signedIn: slot === "public" && signedInHere(), plan, cmp: googleMessageShown() });
  if (mode === "none") return null;
  if (mode === "house") return <House seed={seed || pathname} />;
  if (mode === "consent") return <AdAsk onChoose={(c) => { writeChoice(c); setChoice(c); }} />;
  return <AdBox client={CONFIG.client} slot={CONFIG.slots[slot]} />;
}

/** The slot on a public page: signed-out visitors only, and nothing at all while ads are off. */
export const PublicAd = () => <AdUnit slot="public" />;
