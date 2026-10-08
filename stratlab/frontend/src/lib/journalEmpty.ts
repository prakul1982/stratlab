/** A journal with nothing kept: no trade (real or practice, in any view), none hidden, no imported file. There is nothing
 * to delete then, so the page does not offer "Delete my journal". */
export function journalEmpty(j: { practice_count?: number; real_count?: number; removed?: number; files?: unknown[] }): boolean {
  return (j.practice_count ?? 0) + (j.real_count ?? 0) === 0 && (j.removed ?? 0) === 0 && !(j.files ?? []).length;
}
