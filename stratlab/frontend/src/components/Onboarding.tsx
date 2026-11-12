import { lazy, Suspense, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { useDialogsOpen } from "./kit/Dialog";
import { askWelcome, autoTour, setGuideOpen, TOUR_SEEN, tourSeen } from "../lib/onboarding";
import { declined, loadRun, loadState, offerFor, saveState, tourForFocus, TOUR_IDS, type TourId } from "../lib/intro";
import type { TourStart } from "./Tour";
import { importWithRetry } from "../lib/lazyRetry";

// the pop-ups load when they first open, so they don't slow down the first page
const LevelPrompt = lazy(() => importWithRetry(() => import("./LevelPrompt")).then((m) => ({ default: m.LevelPrompt })));
const Tour = lazy(() => importWithRetry(() => import("./Tour")).then((m) => ({ default: m.Tour })));
const IntroOffer = lazy(() => importWithRetry(() => import("./IntroOffer")).then((m) => ({ default: m.IntroOffer })));

const OPEN_TOUR = "stratlab:tour";
/** Open the tours from anywhere: "Take the tour" in the account menu, /tour and the Help page open the list of tours; a space's
 * id opens that space's tour. */
export const openTour = (tour?: TourId | unknown) => {      // also a click handler as it is (the Help page's button): an event is no tour
  window.dispatchEvent(new CustomEvent(OPEN_TOUR, { detail: { tour: typeof tour === "string" ? tour : undefined } }));
};

const readLocal = () => { try { return localStorage.getItem(TOUR_SEEN); } catch { return "1"; } };
const saveLocal = () => { try { localStorage.setItem(TOUR_SEEN, "1"); } catch { /* private window */ } };
const tell = (body: { welcome?: boolean; tour?: "done" | "skipped" }) => api("/me/onboarding", { method: "PUT", body }).catch(() => undefined);
/** How long someone is on a space's page before its tour is offered: not while they pass through. */
const OFFER_AFTER = 1200;

/** The first-run guide, one piece at a time: the welcome question (on a home page only, once per account), then the tour of the
 * space they picked (once, right after the question), then Home's checklist (FirstSteps waits while either is open). Later, the
 * first time they are in another space, a card offers that space's tour; "Take the tour" opens the list of tours any time. */
export function Onboarding({ main: _main }: { main?: string }) {
  const { me, focus } = useApp();
  const loc = useLocation();
  const [tour, setTour] = useState<TourStart | null>(() => loadRun());     // a reload mid-tour picks it up again
  const [welcomed, setWelcomed] = useState(false);          // answered in this visit: the tour may follow
  const [picked, setPicked] = useState<string | null>(null);  // what they answered, for which tour follows
  const [closedHere, setClosedHere] = useState(false);       // answered or closed here: don't ask again before /me catches up
  const seen = tourSeen(me, readLocal());
  const dialogs = useDialogsOpen();
  const ask = !closedHere && askWelcome(me, loc.pathname);

  // the account doesn't know this browser already saw the tour (it was only kept here): tell it, once
  const told = useRef(false);
  useEffect(() => {
    if (!me || told.current || me.onboarding?.tour || readLocal() !== "1") return;
    told.current = true;
    void tell({ tour: "done" });
  }, [me]);

  useEffect(() => { if (autoTour(welcomed, seen) && !ask) setTour({ tour: tourForFocus(picked ?? focus), step: 0 }); }, [welcomed, seen, ask]);   // eslint-disable-line react-hooks/exhaustive-deps
  // listening before the page is drawn: a "Take the tour" the moment a page shows (useEffect runs after the paint) is never lost
  useLayoutEffect(() => {
    const open = (e: Event) => {
      const t = (e as CustomEvent<{ tour?: TourId }>).detail?.tour;
      setOffer(null);
      setTour(t && TOUR_IDS.includes(t) ? { tour: t, step: 0 } : "pick");
    };
    window.addEventListener(OPEN_TOUR, open);
    return () => window.removeEventListener(OPEN_TOUR, open);
  }, []);
  useEffect(() => { setGuideOpen(ask || !!tour); return () => setGuideOpen(false); }, [ask, tour]);

  // a space's tour, offered the first time they are in it (only to someone who started the intro): after a moment on the page,
  // never over another guide or dialog
  const [offer, setOffer] = useState<TourId | null>(null);
  const [stateTick, setStateTick] = useState(0);
  const quiet = !ask && !tour && dialogs === 0 && !!me;
  useEffect(() => {
    setOffer(null);
    if (!quiet) return;
    const t = offerFor(loadState(me?.id), loc.pathname);
    if (!t) return;
    const id = window.setTimeout(() => setOffer(t), OFFER_AFTER);
    return () => window.clearTimeout(id);
  }, [loc.pathname, quiet, me?.id, stateTick]);

  const closeTour = (done: boolean) => {
    setTour(null);
    setWelcomed(false);
    saveLocal();
    setStateTick((x) => x + 1);
    void tell({ tour: done ? "done" : "skipped" });
  };
  const noThanks = (t: TourId) => { saveState(me?.id, declined(loadState(me?.id), t)); setOffer(null); setStateTick((x) => x + 1); };
  return (
    <Suspense fallback={null}>
      {ask && !tour && <LevelPrompt onDone={async (saved, answered, f) => { setClosedHere(true); setPicked(f ?? null); setWelcomed(answered); await saved; void tell({ welcome: true }); }} />}
      {tour && <Tour key={typeof tour === "string" ? tour : `${tour.tour}`} start={tour} onClose={closeTour} paused={dialogs > 0} />}
      {offer && quiet && <IntroOffer tour={offer} onYes={() => { setOffer(null); setTour({ tour: offer, step: 0 }); }} onNo={() => noThanks(offer)} />}
    </Suspense>
  );
}
