import { useEffect, useId, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Coachmark } from "./kit";
import { findAnchor } from "./kit/Coachmark";
import { Compass, Lens, Lock, Sparkle, Wallet } from "./Icons";
import { holdTourMenu } from "../lib/tourMenu";
import { useApp } from "../lib/app";
import { finished, loadState, onStepPage, planLines, saveRun, saveState, started, stopped, tourOfPath, TOUR_IDS, TOURS, type IntroState, type TourId } from "../lib/intro";
import "./intro.css";

/* The tours (lib/intro.ts has the steps): one note at a time, pointed at the real control on the real page, opening that page
 * itself. On a phone a step about something in the menu opens the menu and points at it there (DI-023). "Take the tour" opens
 * the list of tours first, with where each was left. */

export type TourStart = { tour: TourId; step: number; from?: string } | "pick";
type At = { tour: TourId; step: number };

const ICON: Record<TourId, typeof Compass> = { mine: Compass, trade: Sparkle, invest: Lens, money: Wallet };
const phoneNow = () => { try { return window.matchMedia("(max-width: 900px)").matches; } catch { return false; } };
/** Open or close the phone's menu for a step (Shell listens). While the tour holds it open it is not a modal of its own,
 * so the tour's note keeps the keyboard. */
const holdMenu = holdTourMenu;
const typing = (t: EventTarget | null) => t instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName);

/** The tour. `start`: a tour and step, or "pick" for the list. `paused` hides it while another dialog is open (the search palette
 * a step opened, say), on the same step. `onClose(done)`: true when a tour's last step's Done was pressed. */
export function Tour({ start, onClose, paused = false }: { start: TourStart; onClose: (done: boolean) => void; paused?: boolean }) {
  const { me } = useApp();
  const uid = me?.id;
  const loc = useLocation();
  const nav = useNavigate();
  const [at, setAt] = useState<At | "pick">(start === "pick" ? start : { tour: start.tour, step: start.step });
  // where the tour began: it ends there too, so the person is back where they were (a home page's checklist follows the welcome tour)
  const from = useRef(start !== "pick" && start.from ? start.from : `${loc.pathname}${loc.search}`);
  const [intro, setIntro] = useState<IntroState>(() => loadState(uid));
  const keep = (next: IntroState) => { setIntro(next); saveState(uid, next); };
  const [gaveUp, setGaveUp] = useState("");               // a step whose page couldn't be reached shows where the person is
  const ids = useId();
  const tour = at === "pick" ? null : TOURS[at.tour];
  const i = at === "pick" ? 0 : at.step;
  const step = tour?.steps[i] ?? null;
  const last = !!tour && i === tour.steps.length - 1;
  const phone = phoneNow();
  const inMenu = phone && !!step?.menu;

  // a tour started from the welcome or a space's offer counts as started (offers of the other spaces are on from now)
  useEffect(() => { if (start !== "pick") keep(started(loadState(uid), start.tour)); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  // kept for a reload: the same step comes back
  useEffect(() => { saveRun(at === "pick" ? null : { ...at, from: from.current }); }, [at]);

  // the step's own page: opened when another is showing (the company step opens the first suggested company)
  const onPage = !step || onStepPage(step, loc.pathname) || gaveUp === step.id;
  useEffect(() => {
    if (!step || paused || onPage) return;
    if (step.via) {
      if (loc.pathname !== step.via.page) { nav(step.via.page); return; }
      const born = Date.now();
      const t = window.setInterval(() => {
        const to = findAnchor([step.via!.sel])?.getAttribute("href");
        if (to) { window.clearInterval(t); nav(to); }
        else if (Date.now() - born > 6000) { window.clearInterval(t); setGaveUp(step.id); }
      }, 100);
      return () => window.clearInterval(t);
    }
    if (step.go) nav(step.go);
  }, [step?.id, loc.pathname, paused, onPage]);   // eslint-disable-line react-hooks/exhaustive-deps

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
  useEffect(() => () => { holdMenu(false); }, []);
  if (paused) return null;          // another dialog (the search palette, say) is in front: the tour waits, on the same step
  if ((inMenu && !menuShown) || sliding || !onPage) return null;

  const leave = (done: boolean) => {
    holdMenu(false);
    saveRun(null);
    if (`${loc.pathname}${loc.search}` !== from.current) nav(from.current);
    onClose(done);
  };
  const begin = (t: TourId, from = 0) => { setGaveUp(""); keep(started(intro, t)); setAt({ tour: t, step: from }); };
  const go = (k: number) => { setGaveUp(""); if (tour) setAt({ tour: tour.id, step: k }); };
  // closed part way (Skip, Esc): kept, so the list offers to resume it
  const stop = () => { if (tour) keep(stopped(intro, tour.id, i)); leave(false); };

  if (!tour || !step) return <Picker intro={intro} here={tourOfPath(loc.pathname)} onPick={begin} onClose={() => leave(false)} />;

  const done = () => { keep(finished(intro, tour.id)); leave(true); };
  const next = () => (last ? done() : go(i + 1));
  const back = () => i > 0 && go(i - 1);
  const key = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (typing(e.target) || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key === "ArrowRight" && !last) { e.preventDefault(); next(); }
    else if (e.key === "ArrowLeft" && i > 0) { e.preventDefault(); back(); }
  };
  const act = () => {
    const a = step.act;
    if (!a) return;
    if (a.kind === "search") { window.dispatchEvent(new Event("stratlab:search")); return; }
    const to = findAnchor([a.sel])?.getAttribute("href");
    if (to) { nav(to); go(i + 1); }
  };
  const plan = planLines(step, me?.plan_info?.features, me?.plan);
  // after a tour, the others not yet taken, one tap each
  const others = last ? TOUR_IDS.filter((t) => t !== tour.id && !intro.done.includes(t)) : [];
  const title = `${ids}-t`, body = `${ids}-b`;
  return (
    <Coachmark anchor={step.at} or={step.or} label={`Tour: ${tour.name}`} describedBy={`${title} ${body}`} onClose={stop} onKey={key}
      announce={`${tour.name}, step ${i + 1} of ${tour.steps.length}: ${step.title}.`}>
      <div className="k-spread">
        <span className="k-eyebrow intro-eyebrow">{tour.name} · {i + 1} of {tour.steps.length}</span>
        {!last && <button type="button" className="link k-small" data-close onClick={stop}>Skip tour</button>}
      </div>
      <h2 className="tour-title" id={title}>{step.title}</h2>
      <p className="tour-body" id={body}>{phone && step.phone ? step.phone : step.body}</p>
      {plan.map((l) => <p key={l} className="k-small intro-plan"><Lock size={14} /><span>{l}</span></p>)}
      {step.act && <div><button type="button" className="btn quiet sm" onClick={act}>{step.act.label}</button></div>}
      {others.length > 0 && (
        <div className="intro-next" role="group" aria-label="Another tour">
          <span className="k-small k-muted">Next, a look at</span>
          {others.map((t) => <button key={t} type="button" className="btn quiet sm" onClick={() => { keep(finished(intro, tour.id)); begin(t, 0); }}>{TOURS[t].name}</button>)}
        </div>
      )}
      <div className="k-spread intro-foot">
        <div className="tour-dots" role="tablist" aria-label="Tour steps">
          {tour.steps.map((s, k) => (
            <button key={s.id} type="button" role="tab" tabIndex={-1} aria-selected={k === i} aria-label={`Step ${k + 1}: ${s.title}`} onClick={() => go(k)} />
          ))}
        </div>
        <div className="k-row tour-foot">
          {i > 0 && <button type="button" className="btn quiet sm" onClick={back}>Back</button>}
          {/* one button that becomes Done on the last step, so focus stays on it */}
          <button type="button" className="btn sm" data-autofocus onClick={next}>{last ? "Done" : "Next"}</button>
        </div>
      </div>
    </Coachmark>
  );
}

/** "Take the tour": the four tours, each with what it shows and how far it got; the one for the space showing comes first. */
function Picker({ intro, here, onPick, onClose }: { intro: IntroState; here: TourId | null; onPick: (t: TourId, from?: number) => void; onClose: () => void }) {
  const ids = useId();
  const order = here ? [here, ...TOUR_IDS.filter((t) => t !== here)] : TOUR_IDS;
  return (
    <Coachmark anchor={[]} label="Take a tour" describedBy={`${ids}-l`} onClose={onClose} announce="Take a tour: four short tours, one for each space.">
      <div className="k-spread">
        <span className="k-eyebrow">Tours</span>
        <button type="button" className="link k-small" data-close onClick={onClose}>Close</button>
      </div>
      <h2 className="tour-title">Take a tour</h2>
      <p className="tour-body" id={`${ids}-l`}>Each walks through the real pages in a minute or two. Stop any time: this list picks up where you left off.</p>
      <ul className="intro-pick">
        {order.map((t, k) => {
          const tour = TOURS[t];
          const Icon = ICON[t];
          const resume = intro.at?.tour === t && intro.at.step > 0 && intro.at.step < tour.steps.length ? intro.at.step : 0;
          const status = resume ? `Resume at step ${resume + 1} of ${tour.steps.length}` : intro.done.includes(t) ? `Seen · ${tour.steps.length} steps` : `${tour.steps.length} steps`;
          return (
            <li key={t}>
              <button type="button" className="intro-pick-btn" data-tour={t} data-autofocus={k === 0 ? "" : undefined} onClick={() => onPick(t, resume)}>
                <span className="intro-pick-icon" aria-hidden="true"><Icon size={18} /></span>
                <span className="intro-pick-text">
                  <b>{tour.name}{t === here && <span className="k-small k-muted"> · here now</span>}</b>
                  <span className="k-small k-muted">{tour.line}</span>
                </span>
                <span className={`k-small intro-pick-status${resume ? " on" : ""}`}>{status}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </Coachmark>
  );
}
