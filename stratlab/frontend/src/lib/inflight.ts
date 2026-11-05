/* How many calls to the server are out now (lib/api counts each one), so a page's later cards can start their own as soon as the first
 * screen's calls are back instead of after a fixed pause (LIVE1B-085: My space's Markets strip waited 1.2 s on a page whose first calls
 * were answered in 0.4). Plain module state: no React. */

let out = 0;
const idle = new Set<() => void>();

export const callsInFlight = (): number => out;
export function callStarted(): void { out += 1; }
export function callEnded(): void {
  out = Math.max(0, out - 1);
  if (!out) [...idle].forEach((f) => f());
}
/** Calls `f` each time the last call out is answered. Returns a function that stops it. */
export function onIdle(f: () => void): () => void {
  idle.add(f);
  return () => { idle.delete(f); };
}
