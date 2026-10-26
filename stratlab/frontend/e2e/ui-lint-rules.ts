// UI-LINT: the geometry rules, run inside the page (page.evaluate). One self-contained function: Playwright sends its source
// text to the browser, so nothing outside it may be referenced (no imports, no helpers at module level).
//
// The owner keeps finding layout problems by eye (dead space beside a short card, a "+ Custom" floating beside two wrapped chip
// rows, a four-line hint squeezed under one box of a row, two menu items highlighted at once, one figure said three times on a
// card...). Each rule below is one of those patterns, measured on the drawn page (getBoundingClientRect, computed style),
// never on the source, so it finds the problem whichever component caused it.
//
// Rule list and thresholds (also printed at the top of the report):
//   R1  dead space beside a short card      cards/columns in one visual row (same top +-4px); one has > 120px AND > 30% of the row's
//                                            height unused below its content
//   R2  sparse wide card                    a card wider than 900px and >= 140px tall whose content covers < 55% of its inner width
//   R3  floating control                    a button/chip that is a flex sibling of a chip group wrapped over 2+ rows and not level
//                                            with its first row; or the end control of a row of 3+ controls > 48px from the rest
//   R4  text wrapping inside a button       a button/chip/segmented option/tab whose own text runs on 2+ lines
//   R5  uneven row                          3+ controls in a row: one's height off the median by > 25% and > 16px; fields/stats in a
//                                            row whose controls/values sit at y that differ by > 3px; a segmented option > 1.8x the
//                                            median width and > 80px wider than its text
//   R6  squeezed hint                       a field hint narrower than 40% of its row, 3+ lines, in a row of 2+ fields
//   R7  double highlight                    2+ highlighted items (background) with an active state in one nav/menu; 2+ pressed/checked
//                                            in one segmented group
//   R8  repeated figure                     the same money/percent string 3+ times in one card (tables and charts left out)
//   R9  orphan row                          a grid/wrap row of 4+ equal cards/stats whose last line holds one item (3+1, 4+1, ...)
//   R10 overflow / clipping / overlap       the page scrolls sideways; text cut off by an overflow:hidden box; two text lines whose
//                                            boxes cross each other
//   R11 tiny tap target (phone)             a control < 32px tall on a phone-width screen
//   R12 caption clutter                     a small "Dots: ..." / "Colours: ..." caption right under a list or menu
export interface Violation { rule: string; element: string; key: string; detail: string }
export interface LintOpts { phone: boolean; mark: boolean }
export interface LintResult { violations: Violation[]; counts: Record<string, number>; nodes: number }

export function lintPage(opts: LintOpts): LintResult {
  const vw = document.documentElement.clientWidth;
  const found: { rule: string; el: Element; detail: string }[] = [];
  const add = (rule: string, el: Element, detail: string) => { found.push({ rule, el, detail }); };

  // ---- caches and small helpers ------------------------------------------------------------------------------------
  const rects = new Map<Element, DOMRect>();
  const styles = new Map<Element, CSSStyleDeclaration>();
  const R = (e: Element): DOMRect => { let r = rects.get(e); if (!r) { r = e.getBoundingClientRect(); rects.set(e, r); } return r; };
  const S = (e: Element): CSSStyleDeclaration => { let s = styles.get(e); if (!s) { s = getComputedStyle(e); styles.set(e, s); } return s; };
  const px = (v: string) => parseFloat(v) || 0;
  const alpha = (c: string): number => {
    if (!c || c === "transparent") return 0;
    const m = c.match(/rgba?\(([^)]+)\)/) || c.match(/color\(.*?\/\s*([\d.]+%?)\)/);
    if (!m) return 1;
    const parts = m[1].split(/[ ,/]+/).filter(Boolean);
    if (c.startsWith("rgba") && parts.length >= 4) return parseFloat(parts[3]);
    if (c.startsWith("rgb(") && parts.length >= 4) return parseFloat(parts[3]);       // rgb(r g b / a)
    if (c.startsWith("color(")) return m[1].endsWith("%") ? parseFloat(m[1]) / 100 : parseFloat(m[1]);
    return 1;
  };
  const clsOf = (e: Element): string[] => (typeof (e as HTMLElement).className === "string" ? (e as HTMLElement).className.trim().split(/\s+/).filter(Boolean) : []);
  const textOf = (e: Element) => (e.textContent || (e as HTMLInputElement).placeholder || "").replace(/\s+/g, " ").trim();
  const keyOf = (e: Element) => {
    const c = clsOf(e).filter((x) => !/^(active|on|open|bad|is-|css-|[a-z]+-[0-9a-f]{5,}$)/.test(x)).slice(0, 3);
    return `${e.tagName.toLowerCase()}${c.length ? "." + c.join(".") : ""}`;
  };
  const labelOf = (e: Element) => `${keyOf(e)} "${textOf(e).slice(0, 40)}"`;
  const SKIP = "[aria-hidden=true], [hidden], .sr-only";
  // what a closed <details> holds is laid out but never painted (only its <summary> shows)
  const closedDetails = (e: Element): boolean => { const d = e.closest("details:not([open])"); return !!d && !(e.closest("summary") && d.contains(e.closest("summary"))); };
  // a text line fully outside a box that clips it (a line-clamped paragraph's hidden lines, the rows below a scrolling list's fold)
  const clippedAway = (el: Element, r: { left: number; top: number; right: number; bottom: number }): boolean => {
    for (let p: Element | null = el; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
      const s = S(p);
      if (s.overflowX === "visible" && s.overflowY === "visible") continue;
      const b = R(p);
      if (r.top >= b.bottom - 1 || r.bottom <= b.top + 1 || r.left >= b.right - 1 || r.right <= b.left + 1) return true;
    }
    return false;
  };
  const shown = (e: Element): boolean => {
    const r = R(e);
    if (r.width < 1 || r.height < 1) return false;
    const s = S(e);
    if (s.visibility === "hidden" || s.display === "none" || Number(s.opacity) === 0) return false;
    if (r.right <= 0 || r.left >= vw) return false;                    // the menu drawer, parked off the screen
    if (e.closest(SKIP)) return false;
    if (closedDetails(e)) return false;
    return true;
  };
  const kids = (e: Element): Element[] => Array.from(e.children).filter((c) => shown(c));
  const median = (a: number[]) => { const b = [...a].sort((x, y) => x - y); const n = b.length; return n ? (n % 2 ? b[(n - 1) / 2] : (b[n / 2 - 1] + b[n / 2]) / 2) : 0; };
  const lineH = (e: Element) => { const s = S(e); const l = px(s.lineHeight); return l || px(s.fontSize) * 1.25; };
  const CONTROL = "button, [role=button], a.btn, .k-chip, [role=radio], [role=tab], select, input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=range]):not([type=file])";
  const isControl = (e: Element) => e.matches(CONTROL) && !e.matches(".info-btn, .chip-x");
  const REPLACED = new Set(["IMG", "SVG", "CANVAS", "INPUT", "SELECT", "TEXTAREA", "TABLE", "IFRAME", "VIDEO", "PROGRESS", "METER"]);
  const isCard = (e: Element): boolean => {
    if (!(e instanceof HTMLElement) || e.matches("table, td, th, tr")) return false;
    if (!clsOf(e).some((c) => /card$/.test(c))) return false;
    const s = S(e);
    const border = px(s.borderTopWidth) > 0 && s.borderTopStyle !== "none" && alpha(s.borderTopColor) > 0.02;
    return alpha(s.backgroundColor) > 0.02 || border || s.boxShadow !== "none";
  };
  const inFlow = (e: Element): boolean => {                           // not inside something fixed/absolute (a tooltip, a dock, a badge)
    for (let p: Element | null = e; p && p !== document.body; p = p.parentElement) {
      const pos = S(p).position;
      if (pos === "fixed" || pos === "absolute" || pos === "sticky") return false;
    }
    return true;
  };

  // The painted content of a box: text lines, replaced elements (svg, canvas, table, inputs...) and painted leaf boxes (a bar).
  // `cards` also counts nested card boxes (for a column that holds cards). bottomEl: the element that reaches lowest.
  interface Box { l: number; t: number; r: number; b: number; bottomEl: Element | null; text: number; parts: { l: number; t: number; r: number; b: number; el: Element }[] }
  const contentBox = (root: Element, cards: boolean): Box | null => {
    const box: Box = { l: Infinity, t: Infinity, r: -Infinity, b: -Infinity, bottomEl: null, text: 0, parts: [] };
    const grow = (r: { left: number; top: number; right: number; bottom: number }, el: Element) => {
      if (r.right - r.left < 0.5 || r.bottom - r.top < 0.5) return;
      box.parts.push({ l: r.left, t: r.top, r: r.right, b: r.bottom, el });
      box.l = Math.min(box.l, r.left); box.t = Math.min(box.t, r.top); box.r = Math.max(box.r, r.right);
      if (r.bottom > box.b) { box.b = r.bottom; box.bottomEl = el; }
    };
    const words = (c: Element) => {
      for (const n of Array.from(c.childNodes)) {
        if (n.nodeType === 3 && (n.textContent || "").trim()) {
          const rg = document.createRange(); rg.selectNodeContents(n);
          for (const lr of Array.from(rg.getClientRects())) if (!clippedAway(c, lr)) grow(lr, c);
          box.text += (n.textContent || "").trim().length;
        }
      }
    };
    words(root);
    const walk = (e: Element) => {
      for (const c of Array.from(e.children)) {
        if (c.matches(SKIP) || !shown(c)) continue;
        const s = S(c);
        if (s.position === "fixed") continue;
        const tag = c.tagName.toUpperCase();
        if (REPLACED.has(tag)) { grow(R(c), c); continue; }
        if (cards && isCard(c)) grow(R(c), c);
        words(c);
        if (!c.children.length && (alpha(s.backgroundColor) > 0.05 || px(s.borderTopWidth) > 0) && R(c).height >= 2) grow(R(c), c);
        walk(c);
      }
    };
    walk(root);
    return box.b === -Infinity ? null : box;
  };
  const padBottom = (e: Element) => px(S(e).paddingBottom) + px(S(e).borderBottomWidth);
  // the bottom edge of what a box really needs: its lowest content plus the bottom padding of every card around that content
  const usedBottom = (item: Element, box: Box): number => {
    let b = box.b;
    for (let p: Element | null = box.bottomEl; p; p = p.parentElement) {
      if (p === item) { if (isCard(item)) b += padBottom(item); break; }
      if (isCard(p)) b += padBottom(p);
    }
    return b;
  };
  const rowsOf = (items: Element[], tol: number): Element[][] => {   // items that sit in one visual row: tops within tol
    const rows: Element[][] = [];
    for (const it of [...items].sort((a, b) => R(a).top - R(b).top || R(a).left - R(b).left)) {
      const last = rows[rows.length - 1];
      if (last && Math.abs(R(last[0]).top - R(it).top) <= tol) last.push(it); else rows.push([it]);
    }
    return rows;
  };
  const all = Array.from(document.querySelectorAll("body *"));
  const flexish = (s: CSSStyleDeclaration) => /flex|grid/.test(s.display);

  // ---- R1 dead space beside a short card ---------------------------------------------------------------------------
  for (const p of all) {
    const s = S(p);
    if (!flexish(s) || p.matches(SKIP) || !shown(p)) continue;
    if (s.display.includes("flex") && s.flexDirection.startsWith("column")) continue;
    const items = kids(p).filter((c) => R(c).width >= 140 && R(c).height >= 40 && S(c).position !== "absolute" && S(c).position !== "fixed");
    for (const row of rowsOf(items, 4)) {
      if (row.length < 2) continue;
      const xs = [...row].sort((a, b) => R(a).left - R(b).left);
      if (xs.some((a, i) => i && R(a).left < R(xs[i - 1]).right - 2)) continue;     // overlapping: not side by side
      if (row.some((c) => c.matches("aside, nav, header, footer, main, [role=navigation]"))) continue;          // the page's own chrome (sidebar, admin menu) is not a card row
      const cardish = row.filter((c) => isCard(c) || c.querySelector("[class*=card]"));
      if (cardish.length < 2) continue;
      const top = Math.min(...row.map((c) => R(c).top));
      const bottom = Math.max(...row.map((c) => R(c).bottom));
      const rowH = bottom - top;
      for (const it of cardish) {
        const box = contentBox(it, true);
        if (!box) continue;
        const dead = bottom - usedBottom(it, box);
        if (dead > 120 && dead / rowH > 0.3) add("R1", it, `${Math.round(dead)}px of ${Math.round(rowH)}px row height empty under it (content ends ${Math.round(usedBottom(it, box) - top)}px down; ${row.length} side by side)`);
      }
    }
  }

  // ---- R2 sparse wide card -------------------------------------------------------------------------------------------
  for (const c of all) {
    if (!isCard(c) || !shown(c)) continue;
    const r = R(c);
    if (r.width <= 900 || r.height < 140) continue;
    if (c.querySelector("input, select, textarea")) continue;            // a form: its boxes have their own widths (R5/R6 look at those)
    const box = contentBox(c, false);
    if (!box || !box.text) continue;
    const s = S(c);
    const inner = r.width - px(s.paddingLeft) - px(s.paddingRight) - px(s.borderLeftWidth) - px(s.borderRightWidth);
    const used = box.r - box.l;
    // a long caption can stretch the union over most of the card while its figures sit to the left (the old FII/DII card: two stats
    // in the left 72%): so the figures and fields alone (no paragraph, heading or summary) must also reach 75% of the inner width
    const inL = r.left + px(s.paddingLeft) + px(s.borderLeftWidth);
    const figs = box.parts.filter((q) => !q.el.closest("p, h1, h2, h3, h4, h5, h6, summary, .k-card-head"));
    const figReach = figs.length >= 2 ? (Math.max(...figs.map((q) => q.r)) - inL) / inner : 1;
    const hasWide = figs.some((q) => REPLACED.has(q.el.tagName.toUpperCase()));
    const cols = [...new Set(figs.map((q) => Math.round(q.l / 40)))].length >= 2 && Math.max(...figs.map((q) => q.l)) - Math.min(...figs.map((q) => q.l)) > 150;     // figures side by side, not a left-aligned list
    if (used / inner < 0.55 || (figReach < 0.75 && cols && !hasWide && figs.length >= 3)) add("R2", c, `content spans ${Math.round(used)}px of ${Math.round(inner)}px (${Math.round((100 * used) / inner)}%); its figures reach ${Math.round(100 * figReach)}% of the width, in a ${Math.round(r.width)}x${Math.round(r.height)} card`);
  }

  // ---- R3 floating control -------------------------------------------------------------------------------------------
  for (const p of all) {
    const s = S(p);
    if (!s.display.includes("flex") || s.flexDirection.startsWith("column") || !shown(p)) continue;
    const ks = kids(p);
    if (ks.length < 2) continue;
    for (const c of ks.filter(isControl)) {
      const cr = R(c);
      for (const g of ks) {
        if (g === c) continue;
        const gr = R(g);
        const inner = Array.from(g.querySelectorAll(CONTROL)).filter(shown);
        if (inner.length < 2 || gr.height < 1.8 * cr.height) continue;           // a group of controls wrapped over 2+ rows
        if (cr.top - gr.top > 6) add("R3", c, `sits ${Math.round(cr.top - gr.top)}px below the first row of the ${inner.length} controls beside it (${Math.round(gr.height)}px tall); centre y ${Math.round(cr.top + cr.height / 2)} vs first row ${Math.round(gr.top + cr.height / 2)}`);
      }
    }
    if (!/space-(between|around|evenly)/.test(s.justifyContent)) {
      const cs = ks.filter(isControl).sort((a, b) => R(a).left - R(b).left);
      if (cs.length >= 3) {
        const midY = (e: Element) => R(e).top + R(e).height / 2;
        const sameRow = cs.filter((e) => Math.abs(midY(e) - midY(cs[0])) < 8);
        if (sameRow.length >= 3) {
          const gaps = sameRow.slice(1).map((e, i) => R(e).left - R(sameRow[i]).right);
          for (const [idx, end] of [[0, sameRow[0]], [gaps.length - 1, sameRow[sameRow.length - 1]]] as [number, Element][]) {
            const others = gaps.filter((_, i) => i !== idx);
            if (gaps[idx] > 48 && median(others) <= 20) add("R3", end, `${Math.round(gaps[idx])}px from the rest of its row of ${sameRow.length} controls (the others are ${Math.round(median(others))}px apart)`);
          }
        }
      }
    }
  }

  // ---- R4 text wrapping inside a button ------------------------------------------------------------------------------
  for (const b of all) {
    if (!b.matches("button, [role=button], a.btn, .k-chip, [role=radio], [role=tab]") || b.matches(".info-btn, .chip-x") || !shown(b)) continue;
    if (Array.from(b.querySelectorAll("*")).some((d) => /^(block|flex|grid|list-item|table)/.test(S(d).display) && textOf(d))) continue;   // a tile, not a label
    const tops: number[] = [];
    const w = document.createTreeWalker(b, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      if (!(n.textContent || "").trim() || (n.parentElement && n.parentElement.closest(SKIP))) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      for (const lr of Array.from(rg.getClientRects())) if (lr.width > 1 && !tops.some((t) => Math.abs(t - lr.top) < lineH(b) * 0.5)) tops.push(lr.top);
    }
    if (tops.length >= 2) add("R4", b, `its text runs on ${tops.length} lines in a ${Math.round(R(b).width)}x${Math.round(R(b).height)} button`);
  }

  // ---- R5 uneven rows ------------------------------------------------------------------------------------------------
  for (const p of all) {
    if (!shown(p)) continue;
    const ks = kids(p);
    if (ks.length < 3) continue;
    const ctl = ks.filter((c) => isControl(c) && !c.matches("input"));
    if (ctl.length >= 3) {
      const rows: Element[][] = [];                                  // vertical overlap makes a row (top-aligned, centred or bottom-aligned)
      for (const c of [...ctl].sort((a, b) => R(a).top - R(b).top)) {
        const last = rows[rows.length - 1];
        const lr = last && R(last[0]);
        if (lr && R(c).top < lr.bottom - Math.min(lr.height, R(c).height) * 0.5) last.push(c); else rows.push([c]);
      }
      for (const row of rows) {
        if (row.length < 3) continue;
        const m = median(row.map((c) => R(c).height));
        for (const c of row) {
          const h = R(c).height;
          if (Math.abs(h - m) > 0.25 * m && Math.abs(h - m) > 16) add("R5", c, `${Math.round(h)}px tall in a row of ${row.length} controls whose median is ${Math.round(m)}px`);
        }
      }
    }
    // fields and stats side by side: labels of different line counts push the controls/values to different y
    for (const [sel, inner] of [[".k-field", "input, select, textarea, button:not(.info-btn), .k-input-unit, [role=radiogroup], .k-seg"], [".k-stat", ".k-stat-v"]] as const) {
      const items = ks.filter((c) => c.matches(sel));
      for (const row of rowsOf(items, 6)) {
        if (row.length < 2) continue;
        const ys = row.map((c) => { const t = c.querySelector(inner); return t && shown(t) ? R(t).top : null; });
        const vals = ys.filter((y): y is number => y !== null);
        if (vals.length < 2) continue;
        const lo = Math.min(...vals);
        row.forEach((c, i) => { const y = ys[i]; if (y !== null && y - lo > 3) add("R5", c, `its ${sel === ".k-field" ? "control" : "value"} sits ${Math.round(y - lo)}px lower than its neighbour's in a row of ${row.length} (the label above wraps differently)`); });
      }
    }
  }
  for (const g of all.filter((e) => e.matches(".k-seg, [role=radiogroup], [role=tablist]") && shown(e))) {
    const opts = kids(g).filter((c) => c.matches("button, [role=radio], [role=tab], label"));
    if (opts.length < 3) continue;
    const m = median(opts.map((o) => R(o).width));
    for (const o of opts) {
      const tw = (() => { const rg = document.createRange(); rg.selectNodeContents(o); return rg.getBoundingClientRect().width; })();
      if (R(o).width > 1.8 * m && R(o).width - tw > 80) add("R5", o, `option is ${Math.round(R(o).width)}px wide for ${Math.round(tw)}px of text (the group's median is ${Math.round(m)}px)`);
    }
  }

  // ---- R6 squeezed hint ----------------------------------------------------------------------------------------------
  for (const h of all) {
    if (!h.matches(".k-field-msg, .hint, [class*=hint]") || h.matches(".kbd-hint, .ch-hint, .k-hint-line") || !shown(h)) continue;
    const field = h.closest(".k-field") || h.parentElement;
    const row = (field && field.parentElement) || null;
    if (!field || !row) continue;
    const sibs = Array.from(row.children).filter((c) => shown(c) && (c.matches(".k-field") || c.querySelector("input, select, textarea")));
    if (sibs.length < 2) continue;
    const lines = Math.round(R(h).height / lineH(h));
    if (R(h).width < 0.4 * R(row).width && lines >= 3) add("R6", h, `${lines} lines in a ${Math.round(R(h).width)}px column (${Math.round((100 * R(h).width) / R(row).width)}% of its ${Math.round(R(row).width)}px row of ${sibs.length} fields)`);
  }

  // ---- R7 double highlight -------------------------------------------------------------------------------------------
  const ACTIVE = ".active, [aria-current]:not([aria-current=false]), [aria-selected=true]";
  for (const g of all.filter((e) => e.matches("nav, aside, [role=menu], [role=menubar], .side-groups") && shown(e))) {
    if (g.parentElement && g.parentElement.closest("nav, aside, [role=menu], [role=menubar], .side-groups")) continue;     // the outermost menu only
    const lit = Array.from(g.querySelectorAll(ACTIVE)).filter((e) => shown(e) && alpha(S(e).backgroundColor) > 0.04);
    const top = lit.filter((e) => !lit.some((o) => o !== e && o.contains(e)));
    if (top.length >= 2) add("R7", g, `${top.length} items highlighted at once: ${top.slice(0, 4).map((e) => `"${textOf(e).slice(0, 24)}"`).join(", ")}`);
  }
  for (const g of all.filter((e) => e.matches(".k-seg, [role=radiogroup], [role=tablist]") && shown(e))) {
    const on = Array.from(g.querySelectorAll("[aria-pressed=true], [aria-checked=true], [aria-selected=true]")).filter(shown);
    if (on.length >= 2) add("R7", g, `${on.length} options selected in one group: ${on.slice(0, 4).map((e) => `"${textOf(e).slice(0, 20)}"`).join(", ")}`);
  }

  // ---- R8 repeated figure --------------------------------------------------------------------------------------------
  const FIG = /[+\-−–]?[₹$€£]\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:Cr|crore|lakh|L|K|M|B|mn|bn))?|[+\-−–]?\d+(?:\.\d+)?%/g;
  for (const c of all) {
    if (!isCard(c) || !shown(c) || Array.from(c.querySelectorAll("[class*=card]")).some(isCard)) continue;       // the innermost cards only
    const counts = new Map<string, number>();
    const w = document.createTreeWalker(c, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const pe = n.parentElement;
      if (!pe || pe.closest("table, [role=table], [role=grid], svg, .k-tbl-wrap, select, option, script, style, " + SKIP)) continue;
      if (!shown(pe)) continue;
      for (const m of (n.textContent || "").match(FIG) || []) {
        const norm = m.replace(/^[+\-−–]/, "").replace(/\s+/g, "");
        const digits = norm.replace(/\D/g, "");
        if (/%$/.test(norm) && !/\./.test(norm) && !/^[+\-−–]/.test(m) && digits.length < 3) continue;       // "10%": a threshold named in words, not a figure
        if (/^0+(\.0+)?%?$/.test(norm.replace(/[₹$€£,]/g, "")) || norm === "100%" || (!/%/.test(norm) && digits.length < 3)) continue;
        counts.set(norm, (counts.get(norm) || 0) + 1);
      }
    }
    for (const [fig, n] of counts) if (n >= 3) add("R8", c, `"${fig}" appears ${n} times in this card`);
  }

  // ---- R9 orphan row ---------------------------------------------------------------------------------------------------
  for (const p of all) {
    const s = S(p);
    if (!flexish(s) || !shown(p)) continue;
    if (s.display.includes("flex") && (s.flexDirection.startsWith("column") || s.flexWrap === "nowrap")) continue;
    const items = kids(p).filter((c) => R(c).width >= 140 && R(c).height >= 60 && S(c).position !== "absolute");
    if (items.length < 4 || items.length > 12) continue;                   // a long list of cards ends wherever it ends
    const m = median(items.map((c) => R(c).width));
    if (items.some((c) => Math.abs(R(c).width - m) > 0.1 * m)) continue;           // equal tiles only
    const rows = rowsOf(items, 6);
    if (rows.length < 2) continue;
    const n = rows[0].length;
    if (n >= 3 && rows.slice(0, -1).every((r) => r.length === n) && rows[rows.length - 1].length === 1) {
      add("R9", rows[rows.length - 1][0], `last line of a ${n}-wide grid holds this one item alone (${items.length} items: ${(rows.length - 1) * n} + 1)`);
    }
  }

  // ---- R10 overflow, clipping, overlap ---------------------------------------------------------------------------------
  const scrollsOnPurpose = (e: Element) => { for (let p: Element | null = e; p && p !== document.body; p = p.parentElement) if (/(auto|scroll)/.test(S(p).overflowX)) return true; return false; };
  if (document.documentElement.scrollWidth > vw + 1) {
    const wide = all.filter((e) => { const r = R(e); return r.width && r.height && r.right > vw + 1 && !scrollsOnPurpose(e) && shown(e) && !e.closest("svg, .sr-only"); });
    const culprit = wide.filter((e) => !wide.some((o) => o !== e && e.contains(o))).slice(-3);
    add("R10", document.body, `the page scrolls sideways (${document.documentElement.scrollWidth}px on a ${vw}px screen); widest: ${culprit.map((e) => `${labelOf(e)} to ${Math.round(R(e).right)}px`).join("; ") || "unknown"}`);
  }
  for (const e of all) {
    const s = S(e);
    if (!/(hidden|clip)/.test(s.overflowX) || s.textOverflow === "ellipsis" || e.matches("svg, .sr-only, .k-chipbar, .k-tbl-wrap") || !shown(e)) continue;
    if (e.scrollWidth <= e.clientWidth + 2) continue;
    const er = R(e);
    if (er.width < 8) continue;                                          // collapsed on purpose (the long label of a segmented option on a phone)
    const w = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const pe = n.parentElement;
      if (!pe || !(n.textContent || "").trim() || pe.closest("svg, " + SKIP) || S(pe).textOverflow === "ellipsis") continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      const rr = rg.getBoundingClientRect();
      if (rr.right > er.right + 2 && rr.left < er.right && !scrollsOnPurpose(pe.parentElement || pe)) { add("R10", e, `text is cut off at the box edge: "${(n.textContent || "").trim().slice(0, 40)}" reaches ${Math.round(rr.right)}px in a box ending at ${Math.round(er.right)}px`); break; }
    }
  }
  {
    // overlapping text: two text lines (line boxes of text nodes in normal flow) that cross each other
    interface Line { l: number; t: number; r: number; b: number; el: Element }
    const lines: Line[] = [];
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const pe = n.parentElement;
      if (!pe || !(n.textContent || "").trim() || pe.closest("svg, canvas, script, style, select, option, textarea, [role=tooltip], .info-pop, .popover, .palette, " + SKIP) || closedDetails(pe)) continue;
      const pr = R(pe);
      if (pr.width < 1 || pr.height < 1 || S(pe).visibility === "hidden" || pr.right <= 0 || pr.left >= vw || !inFlow(pe) || scrollsOnPurpose(pe)) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      for (const lr of Array.from(rg.getClientRects())) if (lr.width > 3 && lr.height > 5 && !clippedAway(pe, lr)) lines.push({ l: lr.left, t: lr.top, r: lr.right, b: lr.bottom, el: pe });
    }
    lines.sort((a, b) => a.t - b.t);
    let hits = 0;
    for (let i = 0; i < lines.length && hits < 6; i++) {
      for (let j = i + 1; j < lines.length && lines[j].t < lines[i].b; j++) {
        const a = lines[i], b = lines[j];
        if (a.el === b.el || a.el.contains(b.el) || b.el.contains(a.el)) continue;
        const ow = Math.min(a.r, b.r) - Math.max(a.l, b.l), oh = Math.min(a.b, b.b) - Math.max(a.t, b.t);
        if (ow > 4 && oh > 0.4 * Math.min(a.b - a.t, b.b - b.t)) { add("R10", a.el, `overlaps ${labelOf(b.el)} by ${Math.round(ow)}x${Math.round(oh)}px`); hits++; break; }
      }
    }
  }

  // ---- R11 tiny tap targets on a phone -----------------------------------------------------------------------------------
  if (opts.phone) {
    for (const el of all) {
      if (!el.matches("button, select, a, [role=button], textarea, input:not([type=range]):not([type=checkbox]):not([type=radio]):not([type=hidden])")) continue;
      if (el.closest("p, li, td, th, .info-btn, .chip-x, .search-box, .nb-name, [aria-hidden=true]") || el.matches(".info-btn, .chip-x, .sr-only") || S(el).display === "inline") continue;
      if (!shown(el)) continue;
      const h = R(el).height;
      if (h < 32) add("R11", el, `${Math.round(h)}px tall`);
    }
  }

  // ---- R12 caption clutter -----------------------------------------------------------------------------------------------------
  for (const e of all) {
    if (!e.matches("p, small, span, div") || e.children.length > 1 || !shown(e)) continue;
    const t = textOf(e);
    if (t.length >= 60 || !/^(Dots?|Colou?rs?|Badges?|Markers?|Icons?|Legend|Key)\b[^.]{0,12}:/i.test(t)) continue;
    const prev = e.previousElementSibling;
    const LIST = "ul, ol, nav, [role=list], [role=menu], [class*=list], [class*=menu]";
    if (((prev && prev.matches(LIST)) || (prev && e.parentElement && e.parentElement.matches(LIST))) && px(S(e).fontSize) <= 13.5) add("R12", e, `a ${Math.round(px(S(e).fontSize))}px caption under a list explains a decoration`);
  }

  // ---- results ------------------------------------------------------------------------------------------------------------------
  const counts: Record<string, number> = {};
  const seen = new Set<string>();
  const violations: Violation[] = [];
  for (const f of found) {
    const k = `${f.rule}|${f.el === document.body ? "body" : labelOf(f.el)}|${f.detail.slice(0, 40)}`;
    if (seen.has(k)) continue;
    seen.add(k);
    counts[f.rule] = (counts[f.rule] || 0) + 1;
    if (counts[f.rule] <= 25) violations.push({ rule: f.rule, element: f.el === document.body ? "body" : labelOf(f.el), key: f.el === document.body ? "body" : keyOf(f.el), detail: f.detail });
  }
  if (opts.mark) {
    const colour: Record<string, string> = { R1: "#ff2d55", R2: "#ff9500", R3: "#af52de", R4: "#ff3b30", R5: "#ffcc00", R6: "#34c759", R7: "#00c7be", R8: "#5856d6", R9: "#ff2d95", R10: "#ff0000", R11: "#8e8e93", R12: "#a2845e" };
    const st = document.createElement("style");
    st.textContent = Object.entries(colour).map(([r, c]) => `[data-uilint~="${r}"]{outline:3px solid ${c} !important;outline-offset:-2px !important}`).join("\n");
    document.head.appendChild(st);
    for (const f of found) if (f.el !== document.body && f.el instanceof HTMLElement) { const cur = f.el.getAttribute("data-uilint") || ""; if (!cur.split(" ").includes(f.rule)) f.el.setAttribute("data-uilint", (cur + " " + f.rule).trim()); }
  }
  return { violations, counts, nodes: all.length };
}
