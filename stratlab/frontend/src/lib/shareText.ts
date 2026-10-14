/* Words and numbers the share card, the public verdict page and the library form share, free of imports so the unit tests read them directly. */

/** How many honesty checks a verdict ran: its own total, else the checks that weren't skipped (a group skips one). */
export const checksRun = (v: { total?: number; checks: { status: string }[] }) => v.total ?? v.checks.filter((c) => c.status !== "skip").length;

/** The form for updating a published entry starts from what it already says; "A StratLab user" is the empty name. */
export const libraryDraft = (entry: { description?: string; author?: string } | null | undefined, savedAuthor: string) => ({
  desc: entry?.description ?? "",
  author: entry?.author && entry.author !== "A StratLab user" ? entry.author : savedAuthor,
});
