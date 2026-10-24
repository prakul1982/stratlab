/* A notebook's edits on their way to the server (useNotebook in pages/NotebookPage). Edits gather in `pending` and are
 * sent together; a save that fails keeps them, under any edit made since, to be sent again (R5B-001: the edit was
 * dropped before the PUT, so a failed save lost it and Run tested the old rules). */

export type SaveState = "idle" | "saving" | "saved" | "failed";

export interface Saver {
  /** add edits to the next save (a later edit of a field replaces the earlier one) */
  add: (body: Record<string, unknown>) => void;
  /** the edits not on the server yet */
  pending: () => Record<string, unknown>;
  /** Send the edits not saved yet. True once every edit made so far is on the server; false when the save failed (the
   * edits stay for the next try). A save already on its way is waited for first, so nobody goes ahead on rules still
   * being saved. `quiet`: the caller says what went wrong itself. */
  flush: (quiet?: boolean) => Promise<boolean>;
}

export function makeSaver(put: (body: Record<string, unknown>) => Promise<unknown>, on: {
  state: (s: SaveState) => void; saved?: (body: Record<string, unknown>) => void; failed?: (e: unknown, quiet: boolean) => void;
}): Saver {
  let pending: Record<string, unknown> = {};
  let inflight: Promise<boolean> | null = null;
  const save = async (quiet: boolean): Promise<boolean> => {
    if (!Object.keys(pending).length) return true;
    const body = pending;
    pending = {};
    on.state("saving");
    try {
      await put(body);
      on.state(Object.keys(pending).length ? "idle" : "saved");
      on.saved?.(body);
      return true;
    } catch (e) {
      pending = { ...body, ...pending };      // a newer edit of the same field wins
      on.state("failed");
      on.failed?.(e, quiet);
      return false;
    }
  };
  return {
    add: (body) => { Object.assign(pending, body); },
    pending: () => pending,
    flush: (quiet = false) => {
      const prev = inflight;
      const p = prev ? prev.then(() => save(quiet), () => save(quiet)) : save(quiet);
      inflight = p;
      void p.finally(() => { if (inflight === p) inflight = null; });
      return p;
    },
  };
}

/** The questions about an idea cut to what the server keeps (a note of 300 characters, a warning of 300, a fallback of 400, ten
 * of each): sent in one save with a pick of the instrument, a note that was too long would have refused the whole save and
 * lost the pick (DA-003). */
export function fitGaps<G extends { mentioned: string[]; notes: string[]; instName: string | null; instMarket?: string | null; fallback: string;
  answered?: Record<string, string>; warnings?: string[] }>(g: G): G {
  const cut = (x: string, n: number) => (x.length > n ? x.slice(0, n - 1) + "…" : x);
  return {
    ...g,
    mentioned: g.mentioned.map((x) => x.slice(0, 20)).slice(0, 20),
    notes: g.notes.map((x) => cut(x, 300)).slice(0, 10),
    instName: g.instName ? g.instName.slice(0, 80) : null,
    instMarket: g.instMarket ? g.instMarket.slice(0, 10) : null,
    fallback: cut(g.fallback ?? "", 400),
    answered: g.answered ? Object.fromEntries(Object.entries(g.answered).slice(0, 20).map(([k, v]) => [k.slice(0, 20), cut(String(v), 120)])) : undefined,
    warnings: (g.warnings ?? []).map((x) => cut(x, 300)).slice(0, 10),
  };
}
