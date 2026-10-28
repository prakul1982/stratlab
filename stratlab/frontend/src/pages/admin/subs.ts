/* Admin → Money → Subscriptions: the one line over the list (LIVE1C-007). */

type SubLike = { status: string; paid_count: number | null };

/** One line over the subscriptions: how many were started, how many were paid even once, and how many payments failed (LIVE1C-007: 25 bare
 * IDs, every one an unpaid checkout, read as 25 problems). */
export function subsSummary(a: { subscriptions: SubLike[]; failed: unknown[] }): string {
  const started = a.subscriptions.length, paid = a.subscriptions.filter((x) => (x.paid_count ?? 0) > 0).length, failed = a.failed.length;
  const open = a.subscriptions.filter((x) => x.status === "created").length;
  return `${started} started, ${paid} paid, ${failed} failed payment${failed === 1 ? "" : "s"}${open ? `; ${open} ${open === 1 ? "checkout was" : "checkouts were"} opened and never paid` : ""}.`;
}
