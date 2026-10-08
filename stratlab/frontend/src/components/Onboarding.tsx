import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { useDialogsOpen } from "./kit/Dialog";
import { askWelcome, autoTour, setGuideOpen, TOUR_SEEN, tourSeen } from "../lib/onboarding";

// the pop-ups load when they first open, so they don't slow down the first page
const LevelPrompt = lazy(() => import("./LevelPrompt").then((m) => ({ default: m.LevelPrompt })));
const Tour = lazy(() => import("./Tour").then((m) => ({ default: m.Tour })));

const OPEN_TOUR = "stratlab:tour";
/** Open the tour from anywhere (Help in the account menu, the Help page). */
export const openTour = () => window.dispatchEvent(new Event(OPEN_TOUR));

const readLocal = () => { try { return localStorage.getItem(TOUR_SEEN); } catch { return "1"; } };
const saveLocal = () => { try { localStorage.setItem(TOUR_SEEN, "1"); } catch { /* private window */ } };
const tell = (body: { welcome?: boolean; tour?: "done" | "skipped" }) => api("/me/onboarding", { method: "PUT", body }).catch(() => undefined);

/** The first-run guide, one piece at a time: the welcome question (on a home page only, once per account), then the
 * short tour (once, right after the question), then Home's checklist (FirstSteps waits while either is open). */
export function Onboarding() {
  const { me } = useApp();
  const loc = useLocation();
  const [tour, setTour] = useState(false);
  const [welcomed, setWelcomed] = useState(false);          // answered in this visit: the tour may follow
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

  useEffect(() => { if (autoTour(welcomed, seen) && !ask) setTour(true); }, [welcomed, seen, ask]);
  useEffect(() => {
    const open = () => setTour(true);
    window.addEventListener(OPEN_TOUR, open);
    return () => window.removeEventListener(OPEN_TOUR, open);
  }, []);
  useEffect(() => { setGuideOpen(ask || tour); return () => setGuideOpen(false); }, [ask, tour]);

  const closeTour = (done: boolean) => {
    setTour(false);
    setWelcomed(false);
    saveLocal();
    void tell({ tour: done ? "done" : "skipped" });
  };
  return (
    <Suspense fallback={null}>
      {ask && !tour && <LevelPrompt onDone={async (saved) => { setClosedHere(true); setWelcomed(true); await saved; void tell({ welcome: true }); }} />}
      {tour && <Tour onClose={closeTour} paused={dialogs > 0} />}
    </Suspense>
  );
}
