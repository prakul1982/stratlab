/** R21: a theme's deck is made only once the theme's AI map and its checks are in. While they are being written the server answers 202
 * {"preparing": true, "retry_after": s}; the page shows the kit's loading bar and asks again, at most `limitMs` in all, never showing a
 * raw error. The plan's deck count is used only when the file is delivered (the server counts it then). */
export type DeckAnswer = { status: number; json: () => Promise<any>; blob: () => Promise<Blob> };

export const DECK_WAIT_MS = 3 * 60 * 1000;
export const PREPARING = "Preparing the deck: the AI map is being written";

export class DeckNotReady extends Error {
  constructor() { super("The deck is still being prepared: the AI map is being written. Try again in a few minutes."); this.name = "DeckNotReady"; }
}

export async function deckWhenReady(get: () => Promise<DeckAnswer>, opts: { onWait?: (label: string) => void; sleep?: (ms: number) => Promise<void>;
  limitMs?: number; now?: () => number } = {}): Promise<Blob> {
  const sleep = opts.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const now = opts.now ?? (() => Date.now());
  const limit = opts.limitMs ?? DECK_WAIT_MS;
  const start = now();
  for (;;) {
    const res = await get();
    if (res.status !== 202) return res.blob();
    let wait = 10;
    try { const j = await res.json(); wait = Math.min(30, Math.max(3, Number(j?.retry_after) || 10)); } catch { /* the default wait */ }
    if (now() - start + wait * 1000 > limit) throw new DeckNotReady();
    opts.onWait?.(PREPARING);
    await sleep(wait * 1000);
  }
}
