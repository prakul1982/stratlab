import { useState } from "react";
import { Coachmark } from "./kit";

/** One step: a short title and line, pointed at the real control it is about (the desktop menu's, then the phone's
 * top bar's). Four steps, the ones a newcomer needs; every page is also one search away. */
type Step = { title: string; body: string; phone?: string; at: string[] };

export const STEPS: Step[] = [
  { title: "Four spaces", at: [".sidebar .space-switch", ".topbar [aria-label='Open menu']"],
    body: "Mine is your own summary. Trade is for testing trading ideas, Invest for researching companies and Money for what you own.",
    phone: "The menu holds the four spaces. Mine is your own summary. Trade is for testing trading ideas, Invest for researching companies and Money for what you own." },
  { title: "Ask or do anything", at: [".sidebar .search-btn", ".topbar [aria-label='Search or ask anything']"],
    body: "Type a company, a page or an idea, like \"test RSI below 30 on NIFTY\". Ctrl K opens it from any page." },
  { title: "Start here", at: [".sidebar .side-new", ".topbar [aria-label='New notebook']"],
    body: "Each space's main button: New notebook (a trading idea, tested on past prices), Look up a company, or Add your holdings.",
    phone: "New notebook: describe a trading idea in plain words. StratLab turns it into rules and tests them on past prices." },
  { title: "Your account", at: [".sidebar .acct-btn", ".topbar [aria-label='Open menu']"],
    body: "Your plan, settings and dark mode are under your name. Help there opens this tour again.",
    phone: "In the menu, your name at the bottom opens your plan, settings and dark mode. Help there opens this tour again." },
];

const phoneNow = () => { try { return window.matchMedia("(max-width: 900px)").matches; } catch { return false; } };

/** The short tour. `onClose(done)`: true when the last step's Done was pressed, false when it was closed early. */
export function Tour({ onClose }: { onClose: (done: boolean) => void }) {
  const [i, setI] = useState(0);
  const step = STEPS[i];
  const last = i === STEPS.length - 1;
  const phone = phoneNow();
  return (
    <Coachmark anchor={step.at} label="A quick tour" onClose={() => onClose(false)}>
      <div className="k-spread">
        <span className="k-eyebrow">Step {i + 1} of {STEPS.length}</span>
        {!last && <button type="button" className="link k-small" data-close onClick={() => onClose(false)}>Skip tour</button>}
      </div>
      <h2 className="tour-title" aria-live="polite">{step.title}</h2>
      <p className="tour-body">{phone && step.phone ? step.phone : step.body}</p>
      <div className="tour-dots" role="tablist" aria-label="Tour steps">
        {STEPS.map((s, k) => (
          <button key={s.title} type="button" role="tab" tabIndex={-1} aria-selected={k === i} aria-label={`Step ${k + 1}: ${s.title}`} onClick={() => setI(k)} />
        ))}
      </div>
      <div className="k-row tour-foot">
        {i > 0 && <button type="button" className="btn quiet sm" onClick={() => setI(i - 1)}>Back</button>}
        {/* one button that becomes Done on the last step, so focus stays on it */}
        <button type="button" className="btn sm" data-autofocus onClick={last ? () => onClose(true) : () => setI(i + 1)}>{last ? "Done" : "Next"}</button>
      </div>
    </Coachmark>
  );
}
