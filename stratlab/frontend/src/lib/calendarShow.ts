import type { SpaceView } from "./spaces";

/* The one Calendar's filters (cal94, owner 26 Nov: "one Calendar, fixed in the sidebar"). It opens on the dates for where you are:
 * from Trade the market events and F&O expiries, from Money the person's own money dates, from anywhere else every date (your
 * stocks' when you have a watchlist or holdings). The row of filters inside it switches; the choice is the address (so a link
 * shares it) and the last one picked in each space is kept on this device, a convenience only: the page works without it. */

export type CalShow = "all" | "mine" | "events" | "results" | "actions" | "ipos" | "money";

export const CAL_SHOWS: { value: CalShow; label: string }[] = [
  { value: "all", label: "All" }, { value: "mine", label: "My stocks" }, { value: "events", label: "Market events & expiries" },
  { value: "results", label: "Results" }, { value: "actions", label: "Dividends & splits" }, { value: "ipos", label: "IPOs" }, { value: "money", label: "My money dates" },
];

/** Where the last filter picked in each space is kept (per viewer, this device). */
export const CAL_KEPT = "stratlab.cal.show";
export type CalKept = Partial<Record<SpaceView, CalShow>>;

const isShow = (v: unknown): v is CalShow => CAL_SHOWS.some((s) => s.value === v);

/** A kept choice, read safely: a stored value that is no filter (an old or edited one) counts as none. */
export const keptShow = (kept: unknown, space: SpaceView): CalShow | null => {
  const v = kept && typeof kept === "object" ? (kept as Record<string, unknown>)[space] : null;
  return isShow(v) ? v : null;
};

/** The filter a space opens the Calendar on when nothing was picked there yet. */
export function calDefault(space: SpaceView, hasOwn: boolean): CalShow {
  return space === "trade" ? "events" : space === "money" ? "money" : hasOwn ? "mine" : "all";
}

/** A filter's own address. The Calendar's two old addresses are two of its filters, so every link to them (emails, bookmarks, the
 * money calendar's feed page) opens the Calendar on that filter. */
export function calHref(show: CalShow): string {
  return show === "events" ? "/trade/events" : show === "money" ? "/money/calendar" : `/calendar?show=${show}`;
}

/** The filter an address asks for: its own path for the two old addresses, else ?show=, else the older ?type= and ?scope= links. */
export function askedShow(path: string, search: string): CalShow | null {
  const p = path.split(/[?#]/)[0].replace(/(.)\/$/, "$1");
  if (p === "/trade/events") return "events";
  if (p === "/money/calendar") return "money";
  const q = new URLSearchParams(search);
  const show = q.get("show");
  if (isShow(show)) return show;
  const types = (q.get("type") ?? "").split(",").filter(Boolean);
  const OLD: Record<string, CalShow> = { results: "results", action: "actions", ipo: "ipos", event: "events", money: "money" };
  if (types.length === 1 && OLD[types[0]]) return OLD[types[0]];
  const scope = q.get("scope");
  return scope === "mine" ? "mine" : scope === "all" || types.length > 1 ? "all" : null;
}

/** Where the sidebar's fixed Calendar entry opens from a space: the filter last picked there, else that space's own start. */
export function calEntry(space: SpaceView, kept: unknown): string {
  const k = keptShow(kept, space);
  return k ? calHref(k) : space === "trade" ? "/trade/events" : space === "money" ? "/money/calendar" : "/calendar";
}
