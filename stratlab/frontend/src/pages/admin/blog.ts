/* Admin → Data and jobs → Blog: the types the panel reads and how the research run is told. No React here, so the unit tests read it as it is. */
import { ago } from "../../lib/format";

/** One post as the list gives it (no words): `published` false is hidden by an admin; `indexable` false is a day with too little to say. */
export type BlogPost = { slug: string; kind: "brief" | "research"; market: string | null; title: string; summary: string; published_at: string; updated_at: string;
  indexable: boolean; published: boolean };
export type BlogRun = { at?: string; made?: { post: string; slug: string | null; result: string }[]; problems?: string[] };
export type Blog = { posts: BlogPost[]; run: BlogRun; running: boolean; site: string; counts: { posts: number; shown: number; hidden: number; not_indexed: number } };

const RESULT: Record<string, string> = { new: "written", updated: "updated", same: "unchanged", "nothing to say": "not enough data" };

/** The last research run in a line: when, what each post came to, and any problem (a post the data was too thin for is said, not hidden). */
export const runLine = (r: BlogRun): string => {
  if (!r.at) return "The research posts have not been written yet.";
  const done = (r.made ?? []).map((m) => `${m.post} ${RESULT[m.result] ?? m.result}`).join(", ");
  const bad = r.problems?.length ? ` ${r.problems.length === 1 ? "A problem" : `${r.problems.length} problems`}: ${r.problems.join("; ")}` : "";
  return `Research last written ${ago(r.at)}${done ? `: ${done}.` : "."}${bad}`;
};

/** Where a post is a market brief or research, and for which market, in words. */
export const postKind = (p: Pick<BlogPost, "kind" | "market">): string =>
  p.kind === "brief" ? `Market brief${p.market ? ` · ${p.market === "IN" ? "India" : "US"}` : ""}` : "Research";
