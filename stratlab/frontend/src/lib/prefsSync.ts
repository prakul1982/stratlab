/* The account's preferences, saved in the order they were changed (kept apart from the app so it can be tested without it).
 *
 * Each save sends the whole of what it changes (My space's order is sent whole each time), so the last one to reach the server
 * wins. Two saves sent at once could be handled in either order: pressing "Move Markets up" twice quickly left the account on
 * the first move when its request was handled second, and another browser then showed the old order (DI-006, seen as an
 * unreliable browser test). So a save waits for the one before it to be answered.
 *
 * And /me, read while a save is on its way, can answer with what the account held before that save: an older answer laid over
 * the page put a card back where it was before the person moved it. So an answer keeps the changes made after it was asked for. */

export type PrefsPatch = Record<string, unknown>;

export interface PrefsSync {
  /** Send one change after every change before it has been answered; resolves or rejects with this change's own answer. */
  save(patch: PrefsPatch, send: (patch: PrefsPatch) => Promise<unknown>): Promise<void>;
  /** A mark to take when /me is asked for. */
  mark(): number;
  /** The account's prefs from an answer to the ask made at `since`, with the changes made here since then laid over them. */
  overlay<T extends object>(prefs: T, since: number): T;
}

export function prefsSync(keep = 50): PrefsSync {
  let seq = 0;
  let edits: { n: number; patch: PrefsPatch }[] = [];
  let queue: Promise<unknown> = Promise.resolve();
  return {
    save(patch, send) {
      edits.push({ n: ++seq, patch });
      if (edits.length > keep) edits = edits.slice(-keep);
      const run = queue.then(() => send(patch));
      queue = run.catch(() => undefined);        // one save that failed doesn't stop the ones after it
      return run.then(() => undefined);
    },
    mark: () => seq,
    overlay(prefs, since) {
      const later = edits.filter((e) => e.n > since);
      return later.length ? Object.assign({}, prefs, ...later.map((e) => e.patch)) : prefs;
    },
  };
}
