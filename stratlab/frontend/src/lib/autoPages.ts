import { useEffect, useRef, useState } from "react";

/* AUTO-LOAD (site87, owner: "no next page, show more or load more"): a list the server sends a page at a time keeps its first page's rows
 * and adds the next pages' on their own as the reader nears the end of its block (kit DataTable `more`, ScrollList `onEnd`). */
export function useAutoPages<T extends { id: string | number }>(first: { items: T[]; page: number; pages: number } | null,
  fetchPage: (page: number) => Promise<{ items: T[]; page: number }>): { rows: T[]; load: () => void; busy: boolean; done: boolean } {
  const [extra, setExtra] = useState<{ page: number; items: T[] }>({ page: 0, items: [] });
  const [busy, setBusy] = useState(false);
  const firstRef = useRef(first);
  firstRef.current = first;
  useEffect(() => { setExtra({ page: 0, items: [] }); }, [first]);
  const at = first ? Math.max(first.page, extra.page) : 0;
  const seen = new Set(first?.items.map((r) => r.id) ?? []);
  const rows = first ? [...first.items, ...extra.items.filter((r) => !seen.has(r.id))] : [];
  const done = !first || at >= first.pages;
  const load = () => {
    if (!first || busy || done) return;
    const asked = first;
    setBusy(true);
    fetchPage(at + 1)
      .then((x) => setExtra((cur) => (asked !== firstRef.current ? cur : { page: x.page, items: [...cur.items, ...x.items] })))
      .catch(() => undefined)
      .finally(() => setBusy(false));
  };
  return { rows, load, busy, done };
}
