/** Watch an element's size, calling `cb` on the next animation frame rather than inside the observer's own callback.
 * A size change that changes layout inside the callback makes the browser report "ResizeObserver loop completed with
 * undelivered notifications" as a page error (Safari on iPhone, R7T-014); one frame later the layout change is an ordinary
 * one. Several changes in one frame are one call, with the latest entry. Returns the function that stops watching. */
export function watchSize(el: Element, cb: (entry: ResizeObserverEntry | null) => void): () => void {
  if (typeof ResizeObserver === "undefined") return () => {};
  let frame = 0, last: ResizeObserverEntry | null = null;
  const raf = typeof requestAnimationFrame === "function" ? requestAnimationFrame : (f: FrameRequestCallback) => setTimeout(() => f(0), 16) as unknown as number;
  const caf = typeof cancelAnimationFrame === "function" ? cancelAnimationFrame : (id: number) => clearTimeout(id);
  const ro = new ResizeObserver((entries) => {
    last = entries[entries.length - 1] ?? null;
    if (frame) return;
    frame = raf(() => { frame = 0; cb(last); });
  });
  ro.observe(el);
  return () => { if (frame) caf(frame); ro.disconnect(); };
}
