import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore, type RefObject } from "react";
import { useInRouterContext, useLocation } from "react-router-dom";
import { usePersisted } from "../../lib/persist";
import { scrollBehavior } from "../../lib/motion";
import { FOLDS_KEY, ORDER_KEY, foldKey, keptWith, moved, onSectionUser, orders, routeKey, sectionSlug, sectionUser, setSectionUser } from "../../lib/sections";
import { usePopover } from "./Dialog";

/* Every page section can be closed to its header row and moved up or down among the sections beside it, and both are remembered for
 * the person, per page (owner, 7 Nov). The words are in lib/sections.ts; this is the part on the page. A Card with a CardHead gets it
 * by itself; FoldCard keeps its open state the same way. Moving sets each section's CSS `order` inside the box that holds it, so a
 * page's own layout (a column, two cards side by side) stays as it is and a section only swaps places within it. */

export { setSectionUser };

type Folds = Record<string, boolean>;
type Order = Record<string, string[]>;
const NO_FOLDS: Folds = {};
const NO_ORDER: Order = {};

function useUser(): string {
  return useSyncExternalStore(onSectionUser, sectionUser, () => "guest");
}

/** The page (its route, with the thing it shows left out) and the address's #part; null outside a router. */
function useRoute(): { route: string; hash: string } | null {
  const inRouter = useInRouterContext();
  // the same component is always inside a router or always outside it, so the hook below is called the same way every time
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const loc = inRouter ? useLocation() : null;
  return loc ? { route: routeKey(loc.pathname), hash: loc.hash } : null;
}

/** The kept order of the sections on this page (ids, in order), for "On this page" links to follow. */
export function useSectionOrder(): string[] | undefined {
  const user = useUser();
  const at = useRoute();
  const [order] = usePersisted<Order>(`${ORDER_KEY}.${user}`, NO_ORDER);
  return at ? order[at.route] : undefined;
}

/** The sections in a box, in the order they are shown. */
function shownIn(box: Element): HTMLElement[] {
  return (Array.from(box.children) as HTMLElement[]).filter((c) => c.hasAttribute("data-section"))
    .sort((a, b) => (Number(a.style.order) || 0) - (Number(b.style.order) || 0));
}

/* The boxes that have a kept order watch for children added later (a section that loads, a loading bar swapped for its figures), so a
 * new child takes its place too instead of jumping to the top. */
const watched = new WeakMap<Element, { kept: string[]; mo: MutationObserver }>();

function arrange(box: Element | null | undefined, kept: string[] | undefined) {
  if (!box) return;
  const kids = Array.from(box.children) as HTMLElement[];
  const o = orders(kids.map((k) => k.getAttribute("data-section")), kept);
  const w = watched.get(box);
  if (!o) {
    if (w) { w.mo.disconnect(); watched.delete(box); }
    if (box.hasAttribute("data-arranged")) { kids.forEach((k) => { k.style.order = ""; }); box.removeAttribute("data-arranged"); }
    return;
  }
  kids.forEach((k, i) => { if (k.style.order !== String(o[i])) k.style.order = String(o[i]); });
  box.setAttribute("data-arranged", "");
  if (w) w.kept = kept!;
  else {
    const rec = { kept: kept!, mo: new MutationObserver(() => arrange(box, watched.get(box)?.kept)) };
    rec.mo.observe(box, { childList: true });
    watched.set(box, rec);
  }
}

export type SectionFrame = {
  /** the section's name in the kept settings, once it has a title */
  key: string | null;
  open: boolean;
  setOpen: (open: boolean) => void;
  /** the controls are on: a page section with a title, not inside a dialog */
  on: boolean;
  setTitle: (t: string) => void;
  headingId: string | null;
  setHeadingId: (id: string | null) => void;
  move: (by: -1 | 1) => void;
  reset: () => void;
  /** where it can go now: [up, down], and whether the page has an order of its own */
  can: () => { up: boolean; down: boolean; kept: boolean };
};

/** A section's open state and place, kept for the person on this page. `title` is given by a FoldCard; a Card hears it from its CardHead. */
export function useSectionFrame(el: RefObject<HTMLElement | null>, { id, title: given, defaultOpen = true, allowed = true }: {
  id?: string; title?: string; defaultOpen?: boolean; allowed?: boolean;
}): SectionFrame {
  const user = useUser();
  const at = useRoute();
  const [heard, setTitle] = useState("");
  const [headingId, setHeadingId] = useState<string | null>(null);
  const [inside, setInside] = useState(false);
  const title = given ?? heard;
  const key = title || id ? sectionSlug(id, title) : null;
  const on = allowed && !!at && !!key && !!title && !inside;
  const [folds, setFolds] = usePersisted<Folds>(`${FOLDS_KEY}.${user}`, NO_FOLDS);
  const [order, setOrder] = usePersisted<Order>(`${ORDER_KEY}.${user}`, NO_ORDER);
  const fk = at && key ? foldKey(at.route, key) : null;
  const kept = fk ? folds[fk] : undefined;          // true: closed; false: opened (a fold closed by default)
  const linked = !!id && at?.hash === `#${id}`;     // a link to this section opens it
  const persist = on && !!fk;
  const [local, setLocal] = useState(defaultOpen);       // inside a dialog, or with no page to keep it for: open or closed until it goes
  const open = persist ? (kept === undefined ? defaultOpen : !kept) : local;

  useLayoutEffect(() => {
    const node = el.current;
    setInside(!!node?.parentElement?.closest('[role="dialog"], dialog, .modal, [data-arrange="off"]'));
  }, [el]);

  const setOpen = useCallback((o: boolean) => {
    if (!persist || !fk) { setLocal(o); return; }
    setFolds((prev) => {
      const next = { ...prev };
      if (o === defaultOpen) delete next[fk]; else next[fk] = !o;
      return next;
    });
  }, [persist, fk, defaultOpen, setFolds]);

  // a link to a closed section (an address ending #its-id) opens it
  useEffect(() => { if (linked && persist && !open) setOpen(true); }, [linked, persist]);    // eslint-disable-line react-hooks/exhaustive-deps
  // "On this page" and other links into a closed section open it
  useEffect(() => {
    const node = el.current;
    if (!node || !on) return;
    const f = () => setOpen(true);
    node.addEventListener("k-section-open", f);
    return () => node.removeEventListener("k-section-open", f);
  }, [el, on, setOpen]);

  const keptOrder = at ? order[at.route] : undefined;
  const sig = keptOrder ? keptOrder.join("\n") : "";
  useLayoutEffect(() => {
    if (!on) return;
    arrange(el.current?.parentElement, keptOrder);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [on, key, sig, el]);

  const can = () => {
    const node = el.current, box = node?.parentElement;
    const keptHere = !!keptOrder?.length;
    if (!node || !box || !key) return { up: false, down: false, kept: keptHere };
    const d = getComputedStyle(box).display;
    if (!/flex|grid/.test(d)) return { up: false, down: false, kept: keptHere };
    const ids = shownIn(box).map((s) => s.getAttribute("data-section"));
    const i = ids.indexOf(key);
    return { up: i > 0, down: i >= 0 && i < ids.length - 1, kept: keptHere };
  };
  const move = (by: -1 | 1) => {
    const node = el.current, box = node?.parentElement;
    if (!node || !box || !key || !at) return;
    const ids = shownIn(box).map((s) => s.getAttribute("data-section") as string);
    const next = moved(ids, key, by);
    if (next === ids) return;
    setOrder((prev) => ({ ...prev, [at.route]: keptWith(prev[at.route], next) }));
    window.requestAnimationFrame(() => node.scrollIntoView({ block: "nearest", behavior: scrollBehavior() }));
  };
  const reset = () => {
    if (!at) return;
    setOrder((prev) => { const next = { ...prev }; delete next[at.route]; return next; });
  };
  return { key, open, setOpen, on, setTitle, headingId, setHeadingId, move, reset, can };
}

export const SectionCtx = createContext<SectionFrame | null>(null);
export const useSection = () => useContext(SectionCtx);

// three dots drawn by the style sheet, not an svg: a card's first svg is its chart, and checks that measure a chart find that one
const Dots = () => <span className="k-sec-dots" aria-hidden="true" />;

/** The section's "⋯" menu: Move up, Move down, Reset order. */
export function SectionMenu({ frame }: { frame: SectionFrame }) {
  const [open, setOpen] = useState(false);
  const [can, setCan] = useState({ up: false, down: false, kept: false });
  const box = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  usePopover(open, setOpen, btn, pop, { outside: box });
  const items: { label: string; ok: boolean; run: () => void }[] = [
    { label: "Move up", ok: can.up, run: () => frame.move(-1) },
    { label: "Move down", ok: can.down, run: () => frame.move(1) },
    { label: "Reset order", ok: can.kept, run: () => frame.reset() },
  ];
  const key = (e: React.KeyboardEvent) => {
    const step = e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const all = Array.from(pop.current?.querySelectorAll<HTMLElement>("[role=menuitem]") ?? []);
    const i = all.indexOf(document.activeElement as HTMLElement);
    all[(i + step + all.length) % all.length]?.focus();
  };
  return (
    <div className="more-menu k-sec-menu" ref={box}>
      <button ref={btn} type="button" className="k-sec-btn" aria-haspopup="menu" aria-expanded={open} aria-label="Move section"
        aria-describedby={frame.headingId ?? undefined} title="Move this section"
        onClick={() => { if (!open) setCan(frame.can()); setOpen(!open); }}><Dots /></button>
      {open && (
        <div ref={pop} className="more-pop k-sec-pop" role="menu" aria-label="Move section" onKeyDown={key}>
          {items.map((it) => (
            <button key={it.label} type="button" role="menuitem" aria-disabled={!it.ok || undefined} className={it.ok ? undefined : "off"}
              onClick={() => { if (!it.ok) return; setOpen(false); btn.current?.focus(); it.run(); }}>{it.label}</button>
          ))}
        </div>
      )}
    </div>
  );
}

/** The two buttons at the right of a section's header: the menu, and the chevron that closes or opens it. */
export function SectionControls({ frame, fold = true }: { frame: SectionFrame; fold?: boolean }) {
  return (
    <div className="k-sec">
      <SectionMenu frame={frame} />
      {fold && (
        <button type="button" className="k-sec-btn k-sec-fold" aria-expanded={frame.open} aria-label={frame.open ? "Close section" : "Open section"}
          aria-describedby={frame.headingId ?? undefined} title={frame.open ? "Close this section" : "Open this section"}
          onClick={() => frame.setOpen(!frame.open)}><span className="k-sec-chev" aria-hidden="true" /></button>
      )}
    </div>
  );
}

/** Open a closed section from a link into it ("On this page"): the section hears it and opens. */
export function openSection(el: Element | null) {
  el?.closest("[data-section]")?.dispatchEvent(new Event("k-section-open"));
}
