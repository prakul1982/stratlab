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
 * step. The experience level sits above the choices, already set to the middle one; picking what you came for answers
 * both. Neither hides anything, and both can be changed in Settings. */
export function LevelPrompt({ onDone }: { onDone: () => void }) {
  const { level, focus, savePrefs } = useApp();
  const [lvl, setLvl] = useState<Level>(level ?? "some");
  const nav = useNavigate();
  const loc = useLocation();
  const pick = async (f: Focus) => {
    const view = viewForFocus(f)!;
    // on a home page, open the home of what they picked
    if (loc.pathname === "/" || SPACE_HOMES.includes(loc.pathname)) nav(homeOf(view, f), { replace: true });
    track("onboarding answered", { focus: f, level: lvl });
    onDone();
    await savePrefs({ focus: f, level: lvl, space: view });     // closes this: the answers are in
  };
  return (
    <Modal title="What brings you here?" onClose={() => pick(focus ?? "both")}>
      <p className="muted" style={{ marginBottom: 14 }}>StratLab has three spaces: Trade, Invest and Money. We'll open the one you pick. The others stay one tap away, and you can change this any time in Settings.</p>
      <div className="stack" style={{ gap: 6, marginBottom: 14 }}>
        <span className="small muted">How much have you done?</span>
        <div className="seg seg-even" role="radiogroup" aria-label="Experience" style={{ alignSelf: "flex-start" }}>
          {LEVELS.map(([l, title, what]) => <button key={l} role="radio" aria-checked={lvl === l} aria-pressed={lvl === l} title={what} onClick={() => setLvl(l)}>{title}</button>)}
        </div>
      </div>
      <div className="stack" style={{ gap: 10 }}>
        {FOCUSES.map(([f, title, what]) => (
          <button key={f} className="card explore-card" data-focus={f} onClick={() => pick(f)}><b>{title}</b><span className="small muted">{what}</span></button>
        ))}
      </div>
    </Modal>
  );
}
