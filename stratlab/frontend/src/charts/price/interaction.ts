/* Pointer gestures for canvas charts: drag to pan with a kinetic glide after release, wheel and pinch to zoom
 * around the pointer, double-click or double-tap to reset, hover for a crosshair, tap for touch. Knows nothing
 * about what is drawn: the chart answers `down` to claim a drag for itself (moving a drawing, say). */

export interface GestureHandlers {
  /** A press at (x, y). Return true to take the drag (then move/up go to `drag`/`drop`). */
  down?(x: number, y: number, e: PointerEvent): boolean;
  drag?(x: number, y: number, e: PointerEvent): void;
  drop?(x: number, y: number, e: PointerEvent): void;
  pan(dx: number, dy: number, x: number, y: number): void;
  panEnd?(): void;
  zoom(factor: number, x: number, y: number): void;
  hover(x: number, y: number, touch: boolean): void;
  leave(): void;
  tap?(x: number, y: number, e: PointerEvent): void;
  reset?(x: number, y: number): void;
}

/** Wire gestures to an element; returns the function that removes them. */
export function attachGestures(el: HTMLElement, h: GestureHandlers): () => void {
  const pts = new Map<number, { x: number; y: number }>();
  let mode: "none" | "pan" | "own" | "pinch" = "none";
  let start = { x: 0, y: 0 }, moved = false, lastTap = 0;
  let clicks: { x: number; y: number }[] = [];       // the last two mouse clicks, so a double-click is two in one place
  let pinchDist = 0;
  let vel = 0, lastT = 0, glide = 0;
  const local = (e: { clientX: number; clientY: number }) => {
    const r = el.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  const stopGlide = () => { if (glide) cancelAnimationFrame(glide); glide = 0; };

  const onDown = (e: PointerEvent) => {
    if (e.button !== 0 && e.pointerType === "mouse") return;
    stopGlide();
    const p = local(e);
    pts.set(e.pointerId, p);
    el.setPointerCapture?.(e.pointerId);
    if (pts.size === 2) {
      const [a, b] = [...pts.values()];
      pinchDist = Math.hypot(a.x - b.x, a.y - b.y);
      mode = "pinch";
      return;
    }
    start = p; moved = false; vel = 0; lastT = performance.now();
    if (e.pointerType !== "mouse") h.hover(p.x, p.y, true);
    mode = h.down?.(p.x, p.y, e) ? "own" : "pan";
  };

  const onMove = (e: PointerEvent) => {
    const p = local(e);
    if (!pts.has(e.pointerId)) {
      if (e.pointerType === "mouse") h.hover(p.x, p.y, false);
      return;
    }
    const prev = pts.get(e.pointerId)!;
    pts.set(e.pointerId, p);
    if (mode === "pinch" && pts.size >= 2) {
      const [a, b] = [...pts.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      if (pinchDist > 0 && d > 0) h.zoom(d / pinchDist, (a.x + b.x) / 2, (a.y + b.y) / 2);
      pinchDist = d;
      return;
    }
    if (Math.hypot(p.x - start.x, p.y - start.y) > 4) moved = true;
    if (mode === "own") { h.drag?.(p.x, p.y, e); return; }
    if (mode === "pan" && moved) {
      const now = performance.now(), dt = Math.max(1, now - lastT);
      const dx = p.x - prev.x;
      vel = 0.8 * (dx / dt) + 0.2 * vel;
      lastT = now;
      h.pan(dx, p.y - prev.y, p.x, p.y);
      if (e.pointerType === "mouse") h.hover(p.x, p.y, false);
    }
  };

  const onUp = (e: PointerEvent) => {
    if (!pts.has(e.pointerId)) return;
    const p = local(e);
    pts.delete(e.pointerId);
    if (mode === "pinch") { if (pts.size === 0) mode = "none"; return; }
    if (mode === "own") h.drop?.(p.x, p.y, e);
    else if (!moved) {
      clicks = [...clicks.slice(-1), p];
      const now = performance.now();
      if (e.pointerType !== "mouse" && now - lastTap < 320 && h.reset) { h.reset(p.x, p.y); lastTap = 0; }
      else { lastTap = now; h.tap?.(p.x, p.y, e); }
    } else if (mode === "pan") {
      // keep gliding at the release speed, slowing smoothly
      if (performance.now() - lastT > 80) vel = 0;
      let prevT = performance.now();
      const step = (t: number) => {
        const dt = Math.min(48, t - prevT); prevT = t;
        vel *= Math.pow(0.94, dt / 16);
        if (Math.abs(vel) < 0.02) { glide = 0; h.panEnd?.(); return; }
        h.pan(vel * dt, 0, p.x, p.y);
        glide = requestAnimationFrame(step);
      };
      if (Math.abs(vel) > 0.1) glide = requestAnimationFrame(step); else h.panEnd?.();
    }
    mode = "none";
  };

  const onLeave = (e: PointerEvent) => { if (e.pointerType === "mouse" && !pts.size) h.leave(); };

  const onWheel = (e: WheelEvent) => {
    e.preventDefault();
    stopGlide();
    const p = local(e);
    const dy = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY, dx = e.deltaMode === 1 ? e.deltaX * 16 : e.deltaX;
    if (Math.abs(dx) > Math.abs(dy)) { h.pan(-dx, 0, p.x, p.y); h.panEnd?.(); return; }
    h.zoom(Math.exp(-dy * (e.ctrlKey ? 0.01 : 0.0022)), p.x, p.y);
    h.panEnd?.();
  };

  const onDbl = (e: MouseEvent) => {
    const p = local(e);
    // the browser also calls two quick clicks far apart a double-click (placing a drawing, then clicking away)
    if (clicks.length === 2 && Math.hypot(clicks[0].x - clicks[1].x, clicks[0].y - clicks[1].y) < 12) h.reset?.(p.x, p.y);
  };

  el.addEventListener("pointerdown", onDown);
  el.addEventListener("pointermove", onMove);
  el.addEventListener("pointerup", onUp);
  el.addEventListener("pointercancel", onUp);
  el.addEventListener("pointerleave", onLeave);
  el.addEventListener("wheel", onWheel, { passive: false });
  el.addEventListener("dblclick", onDbl);
  return () => {
    stopGlide();
    el.removeEventListener("pointerdown", onDown);
    el.removeEventListener("pointermove", onMove);
    el.removeEventListener("pointerup", onUp);
    el.removeEventListener("pointercancel", onUp);
    el.removeEventListener("pointerleave", onLeave);
    el.removeEventListener("wheel", onWheel);
    el.removeEventListener("dblclick", onDbl);
  };
}
