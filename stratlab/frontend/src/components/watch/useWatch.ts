/* The person's lists and every change to them (MW-1): read once when the panel opens, changed on the page at once and sent in
 * the same moment; a change the server refuses puts the lists back as the server has them and says why. */
import { useCallback, useEffect, useRef, useState } from "react";
import { useApp } from "../../lib/app";
import { createList, deleteList, getLists, putItems, putOrder, renameList, type WatchAnswer } from "../../lib/watchApi";
import { DEFAULT_ID, type WatchItem, type WatchLimits, type WatchList } from "../../lib/watch";

/** The last answer, kept for the page's life: the panel opens on it at once and reads again behind it. */
let kept: WatchAnswer | null = null;
let keptFor: string | null = null;

export function useWatch() {
  const { fail, me } = useApp();
  if (me && keptFor !== me.id) { kept = null; keptFor = me.id; }          // another person signed in on this page: not their lists
  const [data, setData] = useState<WatchAnswer | null>(kept);
  const [failed, setFailed] = useState(false);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const take = useCallback((a: WatchAnswer) => { kept = a; if (alive.current) { setData(a); setFailed(false); } }, []);
  const reload = useCallback(() => getLists().then(take).catch((e) => { if (alive.current && !kept) setFailed(true); else if (alive.current) fail(e); }), [take, fail]);
  useEffect(() => { void reload(); }, [reload, me?.id]);

  /** Change the lists at once on the page, send the change, and take the server's answer; refused: take the server's lists back and say why. */
  const change = useCallback(async (local: (lists: WatchList[]) => WatchList[], send: () => Promise<WatchAnswer>) => {
    if (kept) take({ ...kept, lists: local(kept.lists) });
    try { take(await send()); } catch (e) { fail(e); void reload(); }
  }, [take, fail, reload]);

  const items = (id: string, f: (xs: WatchItem[]) => WatchItem[]) => (ls: WatchList[]) => ls.map((l) => (l.id === id ? { ...l, items: f(l.items) } : l));
  return {
    lists: data?.lists ?? null, limits: (data?.limits ?? null) as WatchLimits | null, failed, reload,
    add: (id: string, it: WatchItem) => {
      const list = kept?.lists.find((l) => l.id === id);
      if (!list || list.items.some((x) => x.id === it.id)) return Promise.resolve();
      return change(items(id, (xs) => [...xs, it]), () => putItems(id, [...list.items, it]));
    },
    set: (id: string, next: WatchItem[]) => change(items(id, () => next), () => putItems(id, next)),
    remove: (id: string, key: string) => {
      const list = kept?.lists.find((l) => l.id === id);
      return list ? change(items(id, (xs) => xs.filter((x) => x.id !== key)), () => putItems(id, list.items.filter((x) => x.id !== key))) : Promise.resolve();
    },
    moveTo: async (from: string, to: string, it: WatchItem) => {
      const a = kept?.lists.find((l) => l.id === from), b = kept?.lists.find((l) => l.id === to);
      if (!a || !b) return;
      if (b.items.some((x) => x.id === it.id)) return change(items(from, (xs) => xs.filter((x) => x.id !== it.id)), () => putItems(from, a.items.filter((x) => x.id !== it.id)));
      // the new list first: if its limit refuses, the instrument stays where it was
      try { take(await putItems(to, [...b.items, it])); take(await putItems(from, a.items.filter((x) => x.id !== it.id))); } catch (e) { fail(e); void reload(); }
    },
    create: async (name: string): Promise<string | null> => {
      try { const a = await createList(name); take(a); return a.lists[a.lists.length - 1].id; } catch (e) { fail(e); return null; }
    },
    rename: (id: string, name: string) => change((ls) => ls.map((l) => (l.id === id ? { ...l, name } : l)), () => renameList(id, name)),
    delete: (id: string) => change((ls) => ls.filter((l) => l.id !== id), () => deleteList(id)),
    order: (ids: string[]) => change((ls) => [ls[0], ...ids.map((i) => ls.find((l) => l.id === i)!).filter(Boolean)], () => putOrder(ids)),
    DEFAULT_ID,
  };
}
