import { useEffect, useRef } from "react";
import { TOURS, type TourId } from "../lib/intro";
import "./intro.css";

/** The first time someone who started the intro is in a space whose tour they haven't taken: a card in the corner offering it.
 * Not a dialog: it takes no focus and nothing on the page moves for it (it floats over the page, under every dialog). */
export function IntroOffer({ tour, onYes, onNo }: { tour: TourId; onYes: () => void; onNo: () => void }) {
  const t = TOURS[tour];
  const box = useRef<HTMLElement>(null);
  // Esc while focus is inside it: "Not now", as for any small panel
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") { e.preventDefault(); onNo(); } };
    el.addEventListener("keydown", k);
    return () => el.removeEventListener("keydown", k);
  }, [onNo]);
  const what = tour === "mine" ? "Getting around" : `${t.name} in ${t.steps.length} steps`;
  return (
    <aside ref={box} className="intro-offer" aria-label={`A short tour of ${t.name}`} data-tour={tour}>
      <p className="k-eyebrow">{tour === "mine" ? "New here?" : `New to ${t.name}?`}</p>
      <p><b>{what}</b>: {t.line.charAt(0).toLowerCase() + t.line.slice(1)}</p>
      <div className="k-row">
        <button type="button" className="btn sm" onClick={onYes}>Show me</button>
        <button type="button" className="btn quiet sm" onClick={onNo}>Not now</button>
      </div>
    </aside>
  );
}
