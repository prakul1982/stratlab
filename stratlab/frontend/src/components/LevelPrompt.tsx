import { Seg } from "./kit";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import type { Focus, Level } from "../lib/types";
import { homeOf, SPACE_HOMES, viewForFocus } from "../lib/spaces";
import { Modal } from "./ui";
import { track } from "../lib/analytics";

export const LEVELS: [Level, string, string][] = [
  ["new", "New to this", "Guided start: examples to try, explanations up front, advanced settings folded away."],
  ["some", "I've done a bit", "The standard layout: every tool one tap away, advanced settings folded until you need them."],
  ["pro", "I do this actively", "Every tool in view, including the advanced ones. Detailed settings stay tidy: open them once and they stay open."],
];

/** What brings someone here, which also picks the space the menu and home page start in. Trade first: the strategy
 * lab is where StratLab began. */
export const FOCUSES: [Focus, string, string][] = [
  ["trade", "Trade", "Test strategies on years of real prices, paper trade them with fake money, and options."],
  ["invest", "Invest", "Research companies: their numbers, filings, red flags, results dates and your watchlist."],
  ["money", "Manage my money", "Your holdings, capital gains tax and everything you own, in one place."],
  ["both", "All of it", "Every space side by side, Trade first."],
];

/** Asked once, after the first sign-in (and again to anyone who answered only one of the two old questions): one short
 * step. The experience level sits above the choices, left for them to pick (the standard layout if they do not); picking what you came for answers
 * both. Neither hides anything, and both can be changed in Settings. */
export function LevelPrompt({ onDone }: { onDone: (saved: Promise<void>) => void }) {
  const { level, focus, savePrefs } = useApp();
  const [chosen, setChosen] = useState<Level | "">(level ?? "");        // nothing is picked for them
  const lvl: Level = chosen || "some";                                 // left alone, the standard layout applies
  const nav = useNavigate();
  const loc = useLocation();
  const pick = (f: Focus) => {
    const view = viewForFocus(f)!;
    // on a home page (the only place this is asked), open the home of what they picked
    if (loc.pathname === "/" || SPACE_HOMES.includes(loc.pathname)) nav(homeOf(view, f), { replace: true });
    track("onboarding answered", { focus: f, level: lvl });
    onDone(savePrefs({ focus: f, level: lvl, space: view }));     // closes this: the answers are in
  };
  return (
    // closing keeps the page as it is: the default answer is saved, so it isn't asked again
    <Modal title="What brings you here?" onClose={() => onDone(savePrefs({ focus: focus ?? "both", level: lvl }))}>
      <div className="k-stack">
        <p className="k-muted">StratLab has four spaces: Trade, Invest, Money and Mine, your own summary of all three. We'll open the one you pick. The others stay one tap away, and you can change this any time in Settings.</p>
        <div className="k-stack snug">
          <span className="k-small k-muted">How much have you done? · optional</span>
          <Seg label="Experience" value={chosen} onChange={(v) => setChosen(v as Level)} options={LEVELS.map(([l, title]) => ({ value: l, label: title }))} />
        </div>
        <div className="k-stack" role="group" aria-label="What brings you here">
          {FOCUSES.map(([f, title, what]) => (
            <button key={f} type="button" className="k-linkcard explore-card" data-focus={f} onClick={() => pick(f)}><b>{title}</b><span className="small muted">{what}</span></button>
          ))}
        </div>
      </div>
    </Modal>
  );
}
