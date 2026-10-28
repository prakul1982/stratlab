// UI-LINT: the geometry rules, run inside the page (page.evaluate). One self-contained function: Playwright sends its source
// text to the browser, so nothing outside it may be referenced (no imports, no helpers at module level).
//
// The owner keeps finding layout problems by eye (dead space beside a short card, a "+ Custom" floating beside two wrapped chip
// rows, a four-line hint squeezed under one box of a row, two menu items highlighted at once, one figure said three times on a
// card...). Each rule below is one of those patterns, measured on the drawn page (getBoundingClientRect, computed style),
// never on the source, so it finds the problem whichever component caused it.
//
// Rule list and thresholds (also printed at the top of the report):
//   R1  dead space beside a short card      cards/columns in one visual row (same top +-4px); one has > 60px AND > 25% of the row's
//                                            height unused below its content (CK-2: was 120px / 30%, which let a 86px / 41% hole through)
//   R2  sparse wide card                    a card wider than 900px and >= 140px tall whose content covers < 55% of its inner width; (CK-2) a row of
//                                            2+ tiles that fills < 60% of the row's width (two tiles in the left half of a four-column grid)
//   R3  floating control                    a button/chip that is a flex sibling of a chip group wrapped over 2+ rows and not level
//                                            with its first row; or the end control of a row of 3+ controls > 48px from the rest
//   R4  text wrapping inside a button       a button/chip/segmented option/tab whose own text runs on 2+ lines
//   R5  uneven row                          3+ controls in a row: one's height off the median by > 25% and > 16px; fields/stats in a
//                                            row whose controls/values sit at y that differ by > 3px; a segmented option > 1.8x the
//                                            median width and > 80px wider than its text
//   R6  squeezed hint                       a field hint narrower than 40% of its row, 3+ lines, in a row of 2+ fields
//   R7  double highlight                    2+ highlighted items (background) with an active state in one nav/menu; 2+ pressed/checked
//                                            in one segmented group
//   R8  repeated figure                     the same money/percent string 3+ times in one card (tables, charts and list entries left out)
//   R9  orphan row                          a grid/wrap row of 4+ equal cards/stats whose last line holds one item (3+1, 4+1, ...)
//   R10 overflow / clipping / overlap       the page scrolls sideways; text cut off by an overflow:hidden box; two text lines whose
//                                            boxes cross each other
//   R11 tiny tap target (phone)             a control < 32px tall on a phone-width screen
//   R12 caption clutter                     a small "Dots: ..." / "Colours: ..." caption right under a list or menu
// CK-2: what the visual review (VR-1) found by eye and the checker could not see, as rules (its "Checker gaps" G1-G14):
//   R13 empty inside a box (G1)             any bordered/filled box >= 140px tall (cards inside cards too, not only side by side): the biggest
//                                            empty band, at the bottom or between two blocks of content (a note pinned to the bottom edge), is
//                                            > 70px AND > 25% of its height (a box whose content is centred is left out)
//   R14 overlay on content (G2)             a fixed/sticky box that is not app chrome (menu, dialog, toast, Market Watch's button and panel) covers text or a control in main by
//                                            > 6px each way, with the page scrolled to the top, middle or bottom
//   R15 icon glued to its label (G3)        an (i) or icon button < 3px from the text beside it while level with it (or overlapping it)
//   R16 uneven stat row (G4)                3+ stat values >= 20px in one group: a word among numbers, a value wrapped over 2+ lines, or
//                                            labels of different heights in one row
//   R17 page frame (G5)                     (across pages: ui-lint.spec.ts) a page whose title top, left or rightmost card edge differs from
//                                            the one most pages share at that width, by > 2px
//   R18 clipped scroller on a phone (G7)    a sideways-scrolling row whose first/last child is cut by the edge (a chip half shown), or a
//                                            table that shows fewer than all its columns
//   R19 wrapped badge (G8)                  a pill/badge/tag/chip (not a button: R4) whose text runs on 2+ lines
//   R20 orphan end control (G11)            a lone control at the end of a row of text, > 250px from where that text ends
//   R21 gap under the page header (G14)     > 56px of nothing between the page header and the first card
//   R22 row tags out of column (G10)        rows of [tag][name]: the name starts at x's that differ by > 4px from row to row
//   R23 header wrap parity (G13)            cards side by side whose headers differ in height by > 12px because one header's controls wrapped
//   R24 faint checkbox (G12)                an unchecked checkbox/radio whose border and fill are both < 3:1 against what is behind it
//   R25 same sentence twice (G9)            the same sentence (>= 30 characters) twice in one card, outside a table's repeating rows
export interface Violation { rule: string; element: string; key: string; detail: string }
export interface LintOpts { phone: boolean; mark: boolean }
export interface PageFrame { h1Top: number; h1Left: number; right: number }
export interface LintResult { violations: Violation[]; counts: Record<string, number>; nodes: number; frame: PageFrame | null }

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
        if (c.matches(SKIP)) continue;
        if (S(c).display === "contents") { walk(c); continue; }       // a wrapper with no box of its own (a phone's chip bar): its children are the content
        if (!shown(c)) continue;
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
        if (dead > 60 && dead / rowH > 0.25) add("R1", it, `${Math.round(dead)}px of ${Math.round(rowH)}px row height empty under it (content ends ${Math.round(usedBottom(it, box) - top)}px down; ${row.length} side by side)`);
      }
    }
  }

  // ---- R2 sparse wide card -------------------------------------------------------------------------------------------
  for (const c of all) {
    if (!isCard(c) || !shown(c)) continue;
    const r = R(c);
    if (r.width <= 900 || r.height < 140) continue;
    if (c.querySelector("input, select, textarea, .k-state")) continue;            // a form (its boxes have their own widths: R5/R6 look at those) or an empty-state message (centred on purpose)
    const box = contentBox(c, false);
    if (!box || !box.text) continue;
    const s = S(c);
    const inner = r.width - px(s.paddingLeft) - px(s.paddingRight) - px(s.borderLeftWidth) - px(s.borderRightWidth);
    const used = box.r - box.l;
    // a long caption can stretch the union over most of the card while its figures sit to the left (the old FII/DII card: two stats
    // in the left 72%): so the figures and fields alone (no paragraph, heading or summary) must also reach 75% of the inner width
    const inL = r.left + px(s.paddingLeft) + px(s.borderLeftWidth);
    const figs = box.parts.filter((q) => !q.el.closest("p, h1, h2, h3, h4, h5, h6, summary, .k-card-head"));
    // a figure: a big, short text with a digit in it (a stat's value); names, words, dates in a list and sentences are not
    const nums = figs.filter((q) => { const t = textOf(q.el); return t.length <= 24 && /\d/.test(t) && q.el.children.length === 0 && px(S(q.el).fontSize) >= 17; });
    // (a figure column that starts in the right half of the card is spread across it, however short its last figure is)
    const figReach = nums.length >= 2 ? Math.max((Math.max(...nums.map((q) => q.r)) - inL) / inner, (Math.max(...nums.map((q) => q.l)) - inL) / inner + 0.25) : 1;
    const hasWide = figs.some((q) => REPLACED.has(q.el.tagName.toUpperCase()));
    const cols = [...new Set(nums.map((q) => Math.round(q.l / 40)))].length >= 2 && Math.max(...nums.map((q) => q.l)) - Math.min(...nums.map((q) => q.l)) > 150;     // figures side by side, not a left-aligned list
    // how many lines of text the card holds under its heading (parts whose tops are within 6px share a line)
    const tops = [...new Set(box.parts.filter((q) => !q.el.closest("h1, h2, h3, h4, h5, h6, summary, .k-card-head")).map((q) => Math.round(q.t / 6)))].length;
    // two ways to be sparse: figures that stay in the left of a wide card (the old FII/DII card: two stats in the left 72%), or content
    // that fills less than 55% of the width with figures in it or with a long column of lines (a list squeezed into the left third).
    // A short card of words (one headline, three lines of a note) or an empty-state message reads fine at its natural width.
    if ((used / inner < 0.55 && (nums.length >= 2 || tops >= 6)) || (figReach < 0.75 && cols && !hasWide && nums.length >= 2)) add("R2", c, `content spans ${Math.round(used)}px of ${Math.round(inner)}px (${Math.round((100 * used) / inner)}%); its figures reach ${Math.round(100 * figReach)}% of the width, ${tops} lines, in a ${Math.round(r.width)}x${Math.round(r.height)} card`);
  }

  // ---- R2 (CK-2) a short list of tiles that leaves much of its row empty --------------------------------------------------------------------
  // two tiles of an Invest page in the left half of a four-column grid: the right half of the row is empty (VR1-021 had kept four-to-a-row widths)
  for (const p of all) {
    const s = S(p);
    if (!flexish(s) || !shown(p) || (s.display.includes("flex") && s.flexDirection.startsWith("column")) || !inFlow(p)) continue;
    const ks = kids(p);
    const tiles = ks.filter((c) => R(c).width >= 140 && R(c).height >= 60 && S(c).position !== "absolute" && (isCard(c) || c.matches(".k-linkcard, [class*=tile]")));
    if (tiles.length < 2 || tiles.length !== ks.length || rowsOf(tiles, 4).length !== 1) continue;
    const pr = R(p);
    const inner = pr.width - px(s.paddingLeft) - px(s.paddingRight) - px(s.borderLeftWidth) - px(s.borderRightWidth);
    if (inner < 600) continue;
    const used = Math.max(...tiles.map((c) => R(c).right)) - Math.min(...tiles.map((c) => R(c).left));
    if ((inner - used) / inner > 0.4) add("R2", p, `${tiles.length} tiles fill ${Math.round((100 * used) / inner)}% of their ${Math.round(inner)}px row, ${Math.round(inner - used)}px of it empty`);
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
        if (cr.top >= gr.bottom - 2) continue;                                      // on a line of its own below the group (a full-width select on a phone): not beside it
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
            // a gap with a label or a title in it ("Or try", "October 2026") is a gap on purpose: the end control belongs to the text beside it
            const a = idx === 0 ? sameRow[0] : sameRow[idx], b = idx === 0 ? sameRow[1] : sameRow[idx + 1];
            const labelled = ks.some((k) => !isControl(k) && textOf(k) && R(k).left >= R(a).right - 2 && R(k).right <= R(b).left + 2 && Math.abs(R(k).top + R(k).height / 2 - midY(a)) < 16);
            if (!labelled && gaps[idx] > 48 && median(others) <= 20) add("R3", end, `${Math.round(gaps[idx])}px from the rest of its row of ${sameRow.length} controls (the others are ${Math.round(median(others))}px apart)`);
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
    for (const [sel, inner] of [[".k-field", "input:not([type=checkbox]):not([type=radio]), select, textarea, button:not(.info-btn), .k-input-unit, [role=radiogroup], .k-seg"], [".k-stat", ".k-stat-v"]] as const) {
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
      // (a list's entries repeat on purpose: a loan's EMI on each month's date, the same fee on each line of a statement)
      if (!pe || pe.closest("table, [role=table], [role=grid], svg, .k-tbl-wrap, select, option, script, style, li, " + SKIP)) continue;
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
      if (!pe || !(n.textContent || "").trim() || pe.closest("svg, canvas, script, style, select, option, textarea, [role=tooltip], .info-pop, .popover, .palette, " + SKIP) || closedDetails(pe) || S(pe).textOverflow === "ellipsis") continue;      // (an ellipsis cuts the line where its box ends: its text range runs on past that, unseen)
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

  // ======== CK-2: what the visual review found by eye (VR-1 "Checker gaps") ====================================================
  const mainEl = document.querySelector("main") || document.body;
  const inMain = (e: Element) => mainEl.contains(e);
  const hasBorder = (s: CSSStyleDeclaration) => (["Top", "Right", "Bottom", "Left"] as const).some((d) => px(s[`border${d}Width` as "borderTopWidth"]) > 0 && s[`border${d}Style` as "borderTopStyle"] !== "none" && alpha(s[`border${d}Color` as "borderTopColor"]) > 0.02);
  // the lines of text a person reads in a box: one rect per line (never the box of a wrapped paragraph)
  const textLines = (root: Element, fn: (r: DOMRect, pe: Element) => void) => {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const pe = n.parentElement;
      if (!pe || !(n.textContent || "").trim() || pe.closest("svg, canvas, script, style, select, option, textarea, " + SKIP) || !shown(pe)) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      for (const lr of Array.from(rg.getClientRects())) if (lr.width > 1 && lr.height > 1 && !clippedAway(pe, lr)) fn(lr, pe);
    }
  };

  // ---- R13 empty inside a box (G1) ---------------------------------------------------------------------------------------
  // R1 compares side-by-side siblings and counts a nested card as the content of its wrapper, so a short card stretched by its row
  // (the home page's "Paper sessions": 110px empty of 287px, inside a .mine-slot) passed. This looks inside every bordered or filled box.
  {
    const flagged: Element[] = [];
    for (const c of all) {
      if (c.matches("main, body, html, aside, nav, header, footer, table, thead, tbody, tfoot, tr, td, th, select, input, textarea, button, svg, canvas, img, option, summary, details, li") || !shown(c) || !inFlow(c)) continue;
      const r = R(c);
      if (r.height < 140 || r.width < 200) continue;
      const s = S(c);
      if (!(hasBorder(s) || alpha(s.backgroundColor) > 0.05)) continue;
      if (c.matches("[role=dialog], [aria-modal=true], .modal, .k-state, [class*=skeleton]") || c.querySelector("[aria-busy=true], .skel, [class*=skeleton]")) continue;       // a dialog or an empty-state message sizes itself; a card still loading is not measured
      const box = contentBox(c, false);
      if (!box) continue;
      // (a chart library draws its canvases in boxes of its own that the walk above does not enter: they are the content too)
      const blocks = box.parts.map((q) => ({ t: q.t, b: q.b }));
      for (const m of Array.from(c.querySelectorAll("canvas, svg, img, video, iframe"))) { const mr = R(m); if (mr.width >= 8 && mr.height >= 8 && !m.closest("[hidden]") && S(m).visibility !== "hidden" && !m.closest(".info-btn, button")) blocks.push({ t: mr.top, b: mr.bottom }); }
      // painted boxes inside it (a tile, an empty-state panel) are content as much as their text, and so is a decorative picture marked aria-hidden
      const drawn = (d: Element) => { const dr = R(d); return dr.width >= 8 && dr.height >= 8 && S(d).display !== "none" && S(d).visibility !== "hidden" && Number(S(d).opacity) > 0 && !closedDetails(d) && dr.right > 0 && dr.left < vw; };
      for (const d of Array.from(c.querySelectorAll("*"))) {
        if (d.closest("svg, .sr-only, [hidden]") || !drawn(d)) continue;
        const ds = S(d);
        const art = d.matches("[aria-hidden=true]") && !d.parentElement?.closest("[aria-hidden=true]");
        if (art || ((hasBorder(ds) || alpha(ds.backgroundColor) > 0.05) && !d.matches(".info-btn, .chip-x"))) blocks.push({ t: R(d).top, b: R(d).bottom });
      }
      const innerTop = r.top + px(s.paddingTop) + px(s.borderTopWidth);
      const innerBottom = r.bottom - padBottom(c);
      // the biggest empty band: content blocks by top, the gap before each one past everything above it, then the gap under the last (a note pinned
      // to the bottom edge leaves its band in the middle: stretching a short card and pinning its notes only moved the hole)
      blocks.sort((x, y) => x.t - y.t);
      let reach = -Infinity, band = 0, from = 0;
      for (const q of blocks) { if (reach > -Infinity && q.t - reach > band) { band = q.t - reach; from = reach; } reach = Math.max(reach, q.b); }
      const lowest = reach;
      const empty = innerBottom - lowest;
      const atBottom = empty > 70 && empty / r.height > 0.25 && box.t - innerTop <= 0.5 * empty;      // (content centred in its box, as a message is, is not a hole at the bottom)
      const inMiddle = band > 70 && band / r.height > 0.25;
      if (atBottom || inMiddle) {
        flagged.push(c);
        found.push({ rule: "R13", el: c, detail: inMiddle && band >= empty ? `a ${Math.round(band)}px empty band (${Math.round((100 * band) / r.height)}%) in a ${Math.round(r.width)}x${Math.round(r.height)} box, ${Math.round(from - r.top)}px down` : `${Math.round(empty)}px empty (${Math.round((100 * empty) / r.height)}%) at the bottom of a ${Math.round(r.width)}x${Math.round(r.height)} box; its content ends ${Math.round(lowest - r.top)}px down` });
      }
    }
    // a box inside a flagged box shares its hole: report the innermost one
    for (const f of flagged) if (flagged.some((o) => o !== f && f.contains(o))) { const i = found.findIndex((x) => x.rule === "R13" && x.el === f); if (i >= 0) found.splice(i, 1); }
  }

  // ---- R15 icon glued to its label (G3) ----------------------------------------------------------------------------------
  for (const b of all) {
    if (!shown(b) || !b.matches("button, [role=button]")) continue;
    const br = R(b);
    const icon = b.matches(".info-btn") || (br.width <= 40 && br.height <= 40 && textOf(b).length <= 2 && !b.matches(".chip-x"));
    if (!icon) continue;
    for (const dir of [-1, 1]) {
      let n: Node | null = dir < 0 ? b.previousSibling : b.nextSibling;
      while (n && n.nodeType === 3 && !(n.textContent || "").trim()) n = dir < 0 ? n.previousSibling : n.nextSibling;
      if (!n) continue;
      if (n.nodeType === 1 && (!shown(n as Element) || (n as Element).matches("svg, button, [role=button], .info-btn, input, select") || S(n as Element).position === "absolute")) continue;
      if (n.nodeType !== 1 && n.nodeType !== 3) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      for (const lr of Array.from(rg.getClientRects())) {
        if (lr.width < 1) continue;
        const vo = Math.min(br.bottom, lr.bottom) - Math.max(br.top, lr.top);
        const gap = dir < 0 ? br.left - lr.right : lr.left - br.right;
        const beside = dir < 0 ? lr.left < br.left : lr.right > br.right;
        if (vo > 4 && beside && gap < 3 && gap > -80) { add("R15", b, `${gap < 0 ? "overlaps" : "is " + Math.round(gap) + "px from"} the text ${dir < 0 ? "before" : "after"} it ("${(n.textContent || "").trim().slice(dir < 0 ? -22 : 0, dir < 0 ? undefined : 22)}")`); break; }
      }
    }
  }

  // ---- R16 uneven stat row (G4) ----------------------------------------------------------------------------------------------
  {
    const groups = new Map<Element, Element[]>();
    for (const st of all) if (st.matches(".k-stat") && shown(st) && st.parentElement) groups.set(st.parentElement, [...(groups.get(st.parentElement) || []), st]);
    const UNIT = /\b(crores?|cr|lakhs?|thousands?|millions?|billions?|trillions?|k|mn|bn|months?|years?|yrs?|days?|weeks?|times|time|shares?|candles?|trades?|points?|pts|lots?|units?|stocks?|companies|sessions?|alerts?|of|a|an|per|and|to|in|on|at|vs|x|am|pm|min|mins|hours?|sec)\b/gi;
    for (const [, items] of groups) {
      if (items.length < 3) continue;
      const vals = items.map((it) => { const v = it.querySelector(".k-stat-v"); return v && shown(v) && px(S(v).fontSize) >= 20 ? { it, v, t: textOf(v), h: R(v).height } : null; }).filter((x): x is { it: Element; v: Element; t: string; h: number } => !!x);
      if (vals.length >= 3) {
        const numeric = vals.filter((x) => /\d/.test(x.t));
        const words = vals.filter((x) => /[A-Za-z]{4,}/.test(x.t.replace(UNIT, "")));
        if (numeric.length >= 3) for (const x of words) add("R16", x.v, `the word value "${x.t.slice(0, 30)}" among ${numeric.length} numbers in one row of figures`);
        const mh = median(vals.map((x) => x.h));
        for (const x of vals) if (x.h > 1.6 * mh && x.h > 30) add("R16", x.v, `the value "${x.t.slice(0, 30)}" wraps to ${Math.round(x.h)}px while its neighbours' are ${Math.round(mh)}px`);
      }
      for (const row of rowsOf(items, 6)) {
        if (row.length < 2) continue;
        const labs = row.map((it) => it.querySelector(".k-stat-k")).filter((l): l is Element => !!l && shown(l));
        if (labs.length < 2) continue;
        // a label of two lines over a one-line one is fine while the figures under them stand level (R5 checks that); what shows is a label's last
        // line sitting at another height (an (i) taller than the text, VR1-149) or a label of 3+ lines (VR1-111) beside one that is a line
        const ends = labs.map((l) => { let b = -Infinity; textLines(l, (lr) => { b = Math.max(b, lr.bottom); }); return b; });
        const lines = labs.map((l) => Math.round(R(l).height / lineH(l)));
        if (Math.max(...ends) - Math.min(...ends) > 3 && ends.every((e) => e > -Infinity)) add("R16", labs[ends.indexOf(Math.min(...ends))], `its label's last line sits ${Math.round(Math.max(...ends) - Math.min(...ends))}px higher than its neighbour's in one row of ${row.length}`);
        else if (Math.max(...lines) >= 3 && Math.min(...lines) <= 1) add("R16", labs[lines.indexOf(Math.max(...lines))], `its label runs on ${Math.max(...lines)} lines beside labels of ${Math.min(...lines)} in one row of ${row.length}`);
      }
    }
  }

  // ---- R18 clipped scroller on a phone (G7) ----------------------------------------------------------------------------------
  if (opts.phone) {
    for (const e of all) {
      if (!/(auto|scroll)/.test(S(e).overflowX) || !shown(e) || e.scrollWidth <= e.clientWidth + 4 || e.matches("body, html, textarea, pre, code")) continue;
      const er = R(e);
      if (er.width < 120) continue;
      const tbl = e.matches("table") ? e : e.querySelector("table");
      if (tbl && shown(tbl)) {
        if (e.closest("[data-grid]")) continue;                      // a grid read across its row on purpose (a period grid, an option chain): its first column stays put
        const row1 = tbl.querySelector("thead tr") || tbl.querySelector("tr");
        const head = row1 ? Array.from(row1.children).filter(shown) : [];
        const cut = head.filter((h) => R(h).right > er.right + 1 || R(h).left < er.left - 1);
        if (cut.length) add("R18", e, `a table of ${head.length} columns shows ${head.length - cut.length} on a phone (${cut.slice(0, 3).map((h) => `"${textOf(h).slice(0, 14)}"`).join(", ")} are off the edge)`);
        continue;
      }
      const ks = Array.from(e.children).filter(shown);
      if (e.children.length > 12) continue;                          // a long strip (14 candle sizes) scrolls on purpose; a row of up to 12 has room to wrap
      const part = ks.filter((k) => { const kr = R(k); return (kr.right > er.right + 1 && kr.left < er.right - 1) || (kr.left < er.left - 1 && kr.right > er.left + 1); });
      if (ks.length >= 2 && part.length) add("R18", e, `${part.length} of ${ks.length} items cut by the edge of a sideways-scrolling row (${part.slice(0, 2).map((k) => `"${textOf(k).slice(0, 18)}"`).join(", ")})`);
    }
  }

  // ---- R19 wrapped badge (G8) ----------------------------------------------------------------------------------------------------
  for (const b of all) {
    if (b.matches("button, [role=button], a.btn, .k-chip, [role=radio], [role=tab], .info-btn, .chip-x, input, select, textarea, option, table, td, th, tr") || !shown(b)) continue;
    const s = S(b);
    const r = R(b);
    const pillish = px(s.borderTopLeftRadius) >= Math.min(r.height, 60) / 2 - 1 && (alpha(s.backgroundColor) > 0.02 || hasBorder(s));
    if (!(pillish || clsOf(b).some((c) => /(^|-)(pill|badge|tag|chip)s?($|-)/.test(c)))) continue;
    if (!b.matches("span, small, a, i, b, em, strong, div, p, li, label") || textOf(b).length > 90) continue;
    if (Array.from(b.querySelectorAll("*")).some((d) => /^(block|flex|grid|list-item|table)/.test(S(d).display) && textOf(d))) continue;   // a box that holds blocks is not a label
    if (/^(block|flex|grid)$/.test(s.display) && r.width > 0.9 * (b.parentElement ? R(b.parentElement).width : 1e9) && r.height > 2.4 * lineH(b)) continue;       // a callout paragraph
    const tops: number[] = [];
    textLines(b, (lr) => { if (!tops.some((t) => Math.abs(t - lr.top) < lineH(b) * 0.5)) tops.push(lr.top); });
    if (tops.length >= 2) add("R19", b, `its text runs on ${tops.length} lines in a ${Math.round(r.width)}x${Math.round(r.height)} badge`);
  }

  // ---- R20 orphan end control (G11) -----------------------------------------------------------------------------------------------
  for (const p of all) {
    const s = S(p);
    if (!s.display.includes("flex") || s.flexDirection.startsWith("column") || !shown(p) || p.matches("thead, nav, header, footer, aside") || !inFlow(p)) continue;
    const ks = kids(p);
    if (ks.length < 2) continue;
    const end = ks[ks.length - 1];
    if (!(isControl(end) || end.matches(".info-btn, .chip-x, a.link-btn, .link-btn")) || end.matches("input, select") || R(end).width > 160) continue;
    const others = ks.slice(0, -1);
    if (others.some((o) => o.matches("h1, h2, h3, h4, h5, h6, .k-card-head, .k-card-title, .k-page-head, [class*=title], [class*=head]") || o.querySelector("h1, h2, h3, h4, h5, h6, .k-card-title") || isControl(o) || o.querySelector(CONTROL))) continue;     // a title with an action (the card's head), or a row with more controls
    let textEnd = -Infinity;
    for (const o of others) textLines(o, (lr) => { if (Math.abs(lr.top + lr.height / 2 - (R(end).top + R(end).height / 2)) < Math.max(R(end).height, lr.height)) textEnd = Math.max(textEnd, lr.right); });
    if (textEnd === -Infinity) continue;
    const gap = R(end).left - textEnd;
    if (gap > 250) add("R20", end, `sits ${Math.round(gap)}px to the right of where its row's text ends (${Math.round(textEnd)}px)`);
  }

  // ---- R21 gap under the page header (G14) ------------------------------------------------------------------------------------------
  {
    const cardsIn = all.filter((c) => inMain(c) && isCard(c) && shown(c) && inFlow(c));
    const first = [...cardsIn].sort((a, b) => R(a).top - R(b).top || R(a).left - R(b).left)[0];
    const h1 = mainEl.querySelector("h1");
    if (first && h1 && shown(h1) && R(first).top > R(h1).top) {
      let above = -Infinity;
      const fr = R(first);
      // what starts above the card counts up to the card's own top: a headline that runs on beside the card (the verdict's hero) leaves no gap
      const take = (r: { bottom: number; top: number }) => { if (r.top <= fr.top + 1) above = Math.max(above, Math.min(r.bottom, fr.top)); };
      textLines(mainEl, (lr, pe) => { if (!first.contains(pe) && inFlow(pe)) take(lr); });
      for (const e of Array.from(mainEl.querySelectorAll(CONTROL + ", svg, canvas, img"))) if (shown(e) && !first.contains(e) && !e.contains(first) && inFlow(e)) take(R(e));
      const gap = fr.top - above;
      if (above > -Infinity && gap > 56) add("R21", first, `${Math.round(gap)}px of nothing between the page header's last line and the first card`);
    }
  }

  // ---- R22 row tags out of column (G10) -------------------------------------------------------------------------------------------------
  for (const p of all) {
    if (!shown(p) || !/(flex|grid|block)/.test(S(p).display)) continue;
    const rows = Array.from(p.children).filter((c) => shown(c) && c.children.length >= 2);
    if (rows.length < 3) continue;
    const lead = rows.map((r) => { const t = Array.from(r.children).find((c) => shown(c)); return t && t.matches(".badge, .k-badge, .pill, [class*=tag], [class*=badge], [class*=pill]") && R(t).width <= 220 ? { r, t } : null; });
    if (lead.some((x) => !x)) continue;
    // the rows stand one under the other (a flex row of items is not a list of rows)
    if (new Set(rows.map((r) => Math.round(R(r).top))).size < rows.length) continue;
    const xs = (lead as { r: Element; t: Element }[]).map(({ t }) => { const nx = t.nextElementSibling && shown(t.nextElementSibling) ? R(t.nextElementSibling).left : null; return nx; });
    if (xs.some((x) => x === null)) continue;
    const v = xs as number[];
    if (Math.max(...v) - Math.min(...v) > 4) add("R22", rows[0], `${rows.length} rows start their name at x = ${Math.round(Math.min(...v))}..${Math.round(Math.max(...v))}px (the tags before them differ in width)`);
  }

  // ---- R23 header wrap parity (G13) ---------------------------------------------------------------------------------------------------------
  for (const p of all) {
    const s = S(p);
    if (!flexish(s) || !shown(p) || (s.display.includes("flex") && s.flexDirection.startsWith("column"))) continue;
    const cs = kids(p).filter((c) => isCard(c) && R(c).width >= 200);
    for (const row of rowsOf(cs, 4)) {
      if (row.length < 2) continue;
      const heads = row.map((c) => Array.from(c.children).find((h) => shown(h) && /head|title/.test(clsOf(h).join(" ")) && h.children.length >= 2) || null);
      const hs = heads.filter((h): h is Element => !!h);
      if (hs.length < 2) continue;
      const min = Math.min(...hs.map((h) => R(h).height));
      for (const h of hs) {
        const tops = [...new Set(Array.from(h.children).filter(shown).map((c) => Math.round(R(c).top / 6)))].length;
        if (R(h).height - min > 12 && tops >= 2) add("R23", h, `this card's header is ${Math.round(R(h).height)}px (its controls wrap under the title) beside headers of ${Math.round(min)}px in the same row`);
      }
    }
  }

  // ---- R24 faint checkbox (G12) --------------------------------------------------------------------------------------------------------------------
  {
    const rgba = (c: string): [number, number, number, number] | null => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(parseFloat); return p.length >= 3 ? [p[0], p[1], p[2], p.length > 3 ? p[3] : 1] : null; };
    const lum = (c: number[]) => { const f = (v: number) => { const x = v / 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
    const over = (top: number[], below: number[]) => { const a = top[3] ?? 1; return [0, 1, 2].map((i) => top[i] * a + below[i] * (1 - a)); };
    const behind = (e: Element): number[] => { let acc: number[] = [255, 255, 255]; const chain: number[][] = []; for (let p: Element | null = e.parentElement; p; p = p.parentElement) { const c = rgba(S(p).backgroundColor); if (c && c[3] > 0) { chain.push(c); if (c[3] >= 1) break; } } for (const c of chain.reverse()) acc = over(c, acc); return acc; };
    const ratio = (a: number[], b: number[]) => { const la = lum(a), lb = lum(b); return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05); };
    for (const c of all) {
      if (!c.matches("input[type=checkbox], input[type=radio]") || !shown(c) || (c as HTMLInputElement).checked) continue;
      const s = S(c);
      if (!/none/.test(s.appearance || (s as unknown as { webkitAppearance: string }).webkitAppearance || "")) continue;        // a native box draws itself
      const bg = behind(c);
      const fill = rgba(s.backgroundColor), line = rgba(s.borderTopColor);
      const seen = [fill && fill[3] > 0.05 ? ratio(over(fill, bg), bg) : 1, line && px(s.borderTopWidth) > 0 && s.borderTopStyle !== "none" && line[3] > 0.05 ? ratio(over(line, bg), bg) : 1];
      if (Math.max(...seen) < 3) add("R24", c, `its border and fill are ${Math.max(...seen).toFixed(1)}:1 against what is behind it (3:1 needed to see the box)`);
    }
  }

  // ---- R25 same sentence twice in one card (G9) ---------------------------------------------------------------------------------------------------
  for (const c of all) {
    if (!isCard(c) || !shown(c) || Array.from(c.querySelectorAll("[class*=card]")).some(isCard)) continue;
    const seenT = new Map<string, Element[]>();
    const w = document.createTreeWalker(c, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const pe = n.parentElement;
      if (!pe || pe.closest("table, [role=table], [role=grid], svg, .k-tbl-wrap, select, option, script, style, li, " + SKIP) || !shown(pe)) continue;
      const t = (n.textContent || "").replace(/\s+/g, " ").trim().replace(/[.:;]+$/, "").toLowerCase();
      if ((pe.textContent || "").replace(/\s+/g, " ").trim() !== (n.textContent || "").replace(/\s+/g, " ").trim()) continue;      // a whole sentence of its own, not the tail of "Last 3 months: X"
      if (t.length >= 30) seenT.set(t, [...(seenT.get(t) || []), pe]);
    }
    // the same words in one entry (a title and then the line under it), not the same caption on each of a card's rows or stats:
    // two different kinds of element, close together
    const sig = (e: Element) => `${e.tagName}.${clsOf(e).join(".")}`;
    for (const [t, els] of seenT) {
      if (els.length < 2) continue;
      for (let i = 0; i < els.length; i++) for (let j = i + 1; j < els.length; j++) {
        if (sig(els[i]) === sig(els[j])) continue;
        let lca: Element | null = els[i];
        while (lca && !lca.contains(els[j])) lca = lca.parentElement;
        if (lca && lca !== document.body && R(lca).height <= 220) { add("R25", c, `"${t.slice(0, 50)}" is said twice in one entry of this card`); i = els.length; break; }
      }
    }
  }

  // ---- R14 overlay on content (G2) --------------------------------------------------------------------------------------------------------------------
  // a fixed/sticky box that is not app chrome: the notebook's "Lab notes" pill sat over a row's delete button, the end of "Edit in words"
  // and the "Testing on" box. Content is measured once on the page, the overlay's own box at the top, middle and bottom of the scroll.
  {
    const CHROME = "header, aside, nav, [role=dialog], [role=alertdialog], [aria-modal=true], [role=status], [role=alert], [role=tooltip], .toast, .modal-back, .scrim, .topbar, .sidebar, .side-show, .side-pop, .side-pop-back, .k-coach, .skip-link, .lp-nav, .info-pop, .popover, .palette, .mw-launch, .mw, table";
    const pos = (e: Element) => S(e).position;
    const overlays = all.filter((e) => (pos(e) === "fixed" || pos(e) === "sticky") && shown(e) && !e.closest(CHROME) && (pos(e) === "fixed" || R(e).width < 0.7 * vw) && !e.matches("body, html"));
    const top = overlays.filter((e) => !overlays.some((o) => o !== e && o.contains(e)));
    if (top.length) {
      const sy = window.scrollY;
      const inOverlay = (e: Element) => { for (let p: Element | null = e; p && p !== document.body; p = p.parentElement) { const q = pos(p); if (q === "fixed" || q === "sticky") return true; } return false; };
      interface Tgt { l: number; t: number; r: number; b: number; what: string; el: Element }
      const tgts: Tgt[] = [];
      textLines(mainEl, (lr, pe) => { if (!inOverlay(pe) && !pe.closest(CHROME) && lr.width < 900) tgts.push({ l: lr.left, t: lr.top + sy, r: lr.right, b: lr.bottom + sy, what: textOf(pe).slice(0, 24), el: pe }); });
      for (const e of Array.from(mainEl.querySelectorAll(CONTROL + ", .info-btn"))) if (shown(e) && !inOverlay(e) && R(e).width < 900) tgts.push({ l: R(e).left, t: R(e).top + sy, r: R(e).right, b: R(e).bottom + sy, what: textOf(e).slice(0, 24) || keyOf(e), el: e });
      const maxY = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
      const stops = [...new Set([0, Math.round(maxY / 2), maxY])];
      const names = ["the top", "the middle", "the bottom"];
      for (const o of top) {
        const hit = new Map<string, string>();
        for (const y of stops) {
          window.scrollTo({ top: y, behavior: "instant" as ScrollBehavior });
          const sy2 = window.scrollY;
          const boxes = [o, ...Array.from(o.querySelectorAll("*"))].filter((d) => { const r = d.getBoundingClientRect(); return r.width >= 8 && r.height >= 8 && r.width <= 480 && r.height <= 240 && shown(d) && (d === o || d.matches(CONTROL) || alpha(getComputedStyle(d).backgroundColor) > 0.1 || hasBorder(getComputedStyle(d))); });
          for (const d of boxes) {
            const r = d.getBoundingClientRect();
            if (r.bottom < 0 || r.top > window.innerHeight) continue;
            for (const t of tgts) {
              if (t.el.contains(o) || o.contains(t.el)) continue;
              const ow = Math.min(r.right, t.r) - Math.max(r.left, t.l), oh = Math.min(r.bottom + sy2, t.b) - Math.max(r.top + sy2, t.t);
              if (ow > 6 && oh > 6) hit.set(t.what || keyOf(t.el), names[stops.indexOf(y)] ?? "the scroll");
            }
          }
        }
        window.scrollTo({ top: sy, behavior: "instant" as ScrollBehavior });
        if (hit.size) add("R14", o, `a ${pos(o)} box covers ${[...hit].slice(0, 3).map(([w, where]) => `"${w}" (at ${where})`).join(", ")}${hit.size > 3 ? ` and ${hit.size - 3} more` : ""}`);
      }
    }
  }

  // ---- the page's frame (R17 compares it across pages: ui-lint.spec.ts) ------------------------------------------------------------------
  let frame: PageFrame | null = null;
  {
    const h1 = mainEl.querySelector("h1") || document.querySelector("h1");
    if (h1 && shown(h1)) {
      const cards = Array.from(mainEl.querySelectorAll("[class*=card]")).filter((e) => isCard(e) && shown(e) && inFlow(e));
      // the page's column: the cards' rightmost edge or the page header's, whichever reaches further (a page of three tiles ends its cards early
      // but its column does not; a column cut short, as /new's was at 920px, does)
      const head = h1.closest("header") || h1.parentElement;
      frame = { h1Top: Math.round(R(h1).top + window.scrollY), h1Left: Math.round(R(h1).left), right: Math.round(Math.max(head ? R(head).right : 0, ...cards.map((e) => R(e).right))) };
    }
  }

  // ---- results ------------------------------------------------------------------------------------------------------------------
  const counts: Record<string, number> = {};
  const seen = new Set<string>();
  const violations: Violation[] = [];
  const r1els = new Set(found.filter((f) => f.rule === "R1").map((f) => f.el));
  for (const f of found) {
    if (f.rule === "R13" && r1els.has(f.el)) continue;                // R1 already says this box has a hole
    const k = `${f.rule}|${f.el === document.body ? "body" : labelOf(f.el)}|${f.detail.slice(0, 40)}`;
    if (seen.has(k)) continue;
    seen.add(k);
    counts[f.rule] = (counts[f.rule] || 0) + 1;
    if (counts[f.rule] <= 25) violations.push({ rule: f.rule, element: f.el === document.body ? "body" : labelOf(f.el), key: f.el === document.body ? "body" : keyOf(f.el), detail: f.detail });
  }
  if (opts.mark) {
    const colour: Record<string, string> = { R1: "#ff2d55", R2: "#ff9500", R3: "#af52de", R4: "#ff3b30", R5: "#ffcc00", R6: "#34c759", R7: "#00c7be", R8: "#5856d6", R9: "#ff2d95", R10: "#ff0000", R11: "#8e8e93", R12: "#a2845e", R13: "#ff6482", R14: "#bf5af2", R15: "#32ade6", R16: "#ffd60a", R17: "#ac8e68", R18: "#64d2ff", R19: "#ff375f", R20: "#30d158", R21: "#0a84ff", R22: "#ff9f0a", R23: "#5e5ce6", R24: "#8e8e93", R25: "#d1d1d6" };
    const st = document.createElement("style");
    st.textContent = Object.entries(colour).map(([r, c]) => `[data-uilint~="${r}"]{outline:3px solid ${c} !important;outline-offset:-2px !important}`).join("\n");
    document.head.appendChild(st);
    for (const f of found) if (f.el !== document.body && f.el instanceof HTMLElement) { const cur = f.el.getAttribute("data-uilint") || ""; if (!cur.split(" ").includes(f.rule)) f.el.setAttribute("data-uilint", (cur + " " + f.rule).trim()); }
  }
  return { violations, counts, nodes: all.length, frame };
}

/** R17 (CK-2, VR-1 G5): the title's top, its left edge and the rightmost card edge are the same on every app page at one width, so the
 *  page does not jump or look cut off on the right when you move between them. A page that differs from the value most pages share
 *  (by more than 2px) is reported. Compared per width, theme and sign-in state; needs a handful of pages to know what "most" is. */
export interface FrameRow { group: string; frame: PageFrame }
export function frameOutliers(rows: FrameRow[], minPages = 8): { index: number; detail: string }[] {
  const out: { index: number; detail: string }[] = [];
  const modal = (vals: number[]): number => { const n = new Map<number, number>(); for (const v of vals) { const k = Math.round(v / 2) * 2; n.set(k, (n.get(k) || 0) + 1); } return [...n].sort((a, b) => b[1] - a[1] || a[0] - b[0])[0]?.[0] ?? 0; };
  for (const g of new Set(rows.map((r) => r.group))) {
    const mine = rows.map((r, index) => ({ r, index })).filter((x) => x.r.group === g);
    if (mine.length < minPages) continue;
    const m = { h1Top: modal(mine.map((x) => x.r.frame.h1Top)), h1Left: modal(mine.map((x) => x.r.frame.h1Left)), right: modal(mine.filter((x) => x.r.frame.right > 0).map((x) => x.r.frame.right)) };
    for (const { r, index } of mine) {
      const why: string[] = [];
      if (Math.abs(r.frame.h1Top - m.h1Top) > 2) why.push(`its title starts ${r.frame.h1Top}px down, where most pages (${mine.filter((x) => Math.abs(x.r.frame.h1Top - m.h1Top) <= 2).length} of ${mine.length}) have it at ${m.h1Top}px`);
      if (Math.abs(r.frame.h1Left - m.h1Left) > 2) why.push(`its title starts ${r.frame.h1Left}px from the left, where most pages have it at ${m.h1Left}px`);
      if (r.frame.right > 0 && Math.abs(r.frame.right - m.right) > 2) why.push(`its cards end at ${r.frame.right}px, where most pages' end at ${m.right}px`);
      if (why.length) out.push({ index, detail: why.join("; ") });
    }
  }
  return out;
}
