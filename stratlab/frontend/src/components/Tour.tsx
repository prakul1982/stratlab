import { useEffect, useRef, useState } from "react";
import { Coachmark } from "./kit";

/** One step: a short title and line, pointed at the real control it is about (the desktop menu's, then the phone's
 * top bar's). Four steps, the ones a newcomer needs; every page is also one search away. `menu`: on a phone the thing is
 * inside the menu, so the step opens the menu and points at it there (DI-023: every phone step pointed at the closed
 * menu button, so nothing being described was ever on screen). */
type Step = { title: string; body: string; phone?: string; at: string[]; menu?: boolean };

/** The steps for the space showing: step 3 names that space's own main button ("Add your holdings" in Money), not always
 * New notebook (DI-023). */
export function tourSteps(main = "New notebook"): Step[] {
  const what = main === "New notebook" ? "New notebook: describe a trading idea in plain words, and StratLab turns it into rules and tests them on past prices."
    : main === "Add your holdings" ? "Add your holdings: bring in your broker's holdings file, or type your shares in, to see their value, gains and tax."
    : `${main}: any Indian or US company's price, numbers, filings and news.`;
  return [
    { title: "Four spaces", at: [".sidebar .space-switch"], menu: true,
      body: "My space is your own summary. Trade is for testing trading ideas, Invest for researching companies and Money for what you own." },
    { title: "Ask or do anything", at: [".sidebar .search-btn", ".topbar [aria-label='Search or ask anything']"],
      body: "Type a company, a page or an idea, like \"test RSI below 30 on NIFTY\". Ctrl K opens it from any page.",
      phone: "Type a company, a page or an idea, like \"test RSI below 30 on NIFTY\". The magnifier at the top opens it from any page." },
    { title: "Start here", at: [".sidebar .side-new", `.topbar [aria-label='${main}']`],
      body: `This space's main button. ${what}` },
    // the button is named Account (with the plan beside it), the theme is in Settings, not in this menu (DI-023), and "Take the tour" is in this
    // menu (LIVE1B-045: "the button with your email's first part", and "Take the tour there" with no tour button in Settings)
    { title: "Your account", at: [".sidebar .acct-btn"], menu: true,
      body: "The Account button opens your plan, Settings and Help. Dark mode is in Settings, under Experience. “Take the tour” in that menu shows this again." },
  ];
}

export const STEPS = tourSteps();

const phoneNow = () => { try { return window.matchMedia("(max-width: 900px)").matches; } catch { return false; } };
/** Open or close the phone's menu for a step (Shell listens). While the tour holds it open it is not a modal of its own,
 * so the tour's note keeps the keyboard. */
const holdMenu = (open: boolean) => { window.dispatchEvent(new CustomEvent("stratlab:tour-menu", { detail: { open } })); };

/** The short tour. `paused` hides it while a dialog is open. `onClose(done)`: true when the last step's Done was pressed, false when it was closed early. */
export function Tour({ onClose, paused = false, main }: { onClose: (done: boolean) => void; paused?: boolean; main?: string }) {
  const [i, setI] = useState(0);
  const steps = tourSteps(main);
  const step = steps[i];
  const last = i === steps.length - 1;
  const phone = phoneNow();
  const inMenu = phone && !!step.menu;
  // the drawer slides in: the pointer waits for it, so it lands on the thing and not where the drawer was
  const [menuShown, setMenuShown] = useState(false);
  // ...and it slides away again after the menu's last step: the pointer waits for that too, or the next step's ring is
  // placed where the menu's own button still was (RC5-002: "Ask or do anything" on a phone ringed the page's heading)
  const [sliding, setSliding] = useState(false);
  const wasInMenu = useRef(false);
  useEffect(() => {
    if (paused) return;
    holdMenu(inMenu);
    let t: number | undefined;
    if (inMenu) t = window.setTimeout(() => setMenuShown(true), 320);
    else {
      setMenuShown(false);
      const leaving = wasInMenu.current;
      setSliding(leaving);
      if (leaving) t = window.setTimeout(() => setSliding(false), 320);
    }
    wasInMenu.current = inMenu;
    return () => window.clearTimeout(t);
  }, [inMenu, paused]);
  useEffect(() => () => holdMenu(false), []);
  if (paused) return null;          // another dialog (the search palette, say) is in front: the tour waits, on the same step
  if ((inMenu && !menuShown) || sliding) return null;
  const finish = (done: boolean) => { holdMenu(false); onClose(done); };
  return (
    <Coachmark anchor={step.at} label="A quick tour" onClose={() => finish(false)}>
      <div className="k-spread">
        <span className="k-eyebrow">Step {i + 1} of {steps.length}</span>
        {!last && <button type="button" className="link k-small" data-close onClick={() => finish(false)}>Skip tour</button>}
      </div>
      <h2 className="tour-title" aria-live="polite">{step.title}</h2>
      <p className="tour-body">{phone && step.phone ? step.phone : step.body}</p>
      <div className="tour-dots" role="tablist" aria-label="Tour steps">
        {steps.map((s, k) => (
          <button key={s.title} type="button" role="tab" tabIndex={-1} aria-selected={k === i} aria-label={`Step ${k + 1}: ${s.title}`} onClick={() => setI(k)} />
        ))}
      </div>
      <div className="k-row tour-foot">
        {i > 0 && <button type="button" className="btn quiet sm" onClick={() => setI(i - 1)}>Back</button>}
        {/* one button that becomes Done on the last step, so focus stays on it */}
        <button type="button" className="btn sm" data-autofocus onClick={last ? () => finish(true) : () => setI(i + 1)}>{last ? "Done" : "Next"}</button>
      </div>
    </Coachmark>
  );
}
