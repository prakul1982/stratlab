import { pageAt, type Located } from "./nav";
import { usePersisted } from "./persist";

const KEY = "stratlab.pins";
const NONE: string[] = [];

/** The pages the person pinned to Mine's sidebar, in the order they pinned them. Kept on this device: the account's
 * saved preferences hold only the experience level, focus and space. Pins naming a page that no longer exists are dropped. */
export function usePins() {
  const [raw, setRaw] = usePersisted<string[]>(KEY, NONE);
  const pins: Located[] = (Array.isArray(raw) ? raw : NONE).map((to) => (typeof to === "string" ? pageAt(to) : null)).filter((l): l is Located => !!l);
  const has = (to: string) => pins.some((l) => l.page.to === to);
  const toggle = (to: string) => setRaw((cur) => {
    const list = Array.isArray(cur) ? cur.filter((x) => typeof x === "string") : [];
    return list.includes(to) ? list.filter((x) => x !== to) : [...list, to];
  });
  return { pins, has, toggle };
}
