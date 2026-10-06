import { useLocation, useNavigate } from "react-router-dom";
import { Seg } from "./kit";

/** A Seg whose choices are two or three views of one page, each at its own address (so links and bookmarks keep working):
 * "List" and "At a glance" on the watchlist, "Index and participants" and "Stock futures" on Positioning. It is the one way
 * a page switches between its views now that the rows of tabs under the menu are gone. */
export function RouteSeg({ label, views }: { label: string; views: { to: string; label: string }[] }) {
  const { pathname, search } = useLocation();
  const nav = useNavigate();
  const here = views.find((v) => v.to === pathname) ?? views[0];
  return <Seg label={label} value={here.to} options={views.map((v) => ({ value: v.to, label: v.label }))} onChange={(to) => { if (to !== pathname) nav(to + (to.startsWith("/research") ? search : "")); }} />;
}

export const WATCH_VIEWS = [{ to: "/research/watchlist", label: "List" }, { to: "/research/investor", label: "At a glance" }];
export const POSITIONING_VIEWS = [{ to: "/trade/positioning", label: "Index and participants" }, { to: "/trade/positioning/stocks", label: "Stock futures" }];
