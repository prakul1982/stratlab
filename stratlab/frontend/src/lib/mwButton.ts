/* Where a signed-in person on a laptop finds Market Watch (item 37, owner 30 Oct: "seems nice, just not aligned properly"). The owner
 * asked to SEE both ways before he picks one; the other is deleted once he has:
 *   "menu":  from 901 to 1599px no floating button; the market-status line at the foot of the menu is the Markets button
 *            (from 1600px the floating "Markets" pill stays as it was);
 *   "float": the round floating button stays, and on 901–1599px the page column is a little narrower on its right, so the button
 *            sits centred in a real margin, 18px clear of the cards (it sat 1px from them at 1280).
 * TEMPORARY switch: localStorage "stratlab.mwButton" = "menu" | "float", or ?mwButton=menu|float on any address (which also keeps
 * it), so the owner can try both on the live site. <body data-mw-button> says which is on (the CSS and the tests read it). */
import { useLayoutEffect, useState } from "react";

export type MwButton = "menu" | "float";
export const MW_BUTTON_KEY = "stratlab.mwButton";
/** Until the owner picks: today's floating button, with the margin fix. */
export const MW_BUTTON_DEFAULT: MwButton = "float";

/** "menu" or "float" from a stored or typed value (a plain word, or the word as JSON), else null. */
export function parseMwButton(v: string | null | undefined): MwButton | null {
  const w = (v ?? "").trim().replace(/^"(.*)"$/, "$1").toLowerCase();
  return w === "menu" || w === "float" ? w : null;
}

/** Which way is on: the address's ?mwButton= first, then the kept choice, then the default. */
export function pickMwButton(search: string, stored: string | null | undefined): MwButton {
  return parseMwButton(new URLSearchParams(search).get("mwButton")) ?? parseMwButton(stored) ?? MW_BUTTON_DEFAULT;
}

function readStored(): string | null {
  try { return localStorage.getItem(MW_BUTTON_KEY); } catch { return null; }     // storage off: the default
}

/** The way that is on for this page load; an address's ?mwButton= is kept for the next ones, and <body> carries it. */
export function applyMwButton(search: string): MwButton {
  const typed = parseMwButton(new URLSearchParams(search).get("mwButton"));
  if (typed) { try { localStorage.setItem(MW_BUTTON_KEY, typed); } catch { /* storage off: this page load only */ } }
  const on = typed ?? parseMwButton(readStored()) ?? MW_BUTTON_DEFAULT;
  document.body.dataset.mwButton = on;
  return on;
}

/** The way that is on, kept in step with the address (the Shell passes its location's search) and with another tab's choice. */
export function useMwButton(search: string): MwButton {
  const [on, setOn] = useState<MwButton>(() => pickMwButton(search, readStored()));
  useLayoutEffect(() => { setOn(applyMwButton(search)); }, [search]);
  useLayoutEffect(() => {
    const f = (e: StorageEvent) => { if (e.key === MW_BUTTON_KEY) setOn(applyMwButton("")); };
    window.addEventListener("storage", f);
    return () => window.removeEventListener("storage", f);
  }, []);
  return on;
}
