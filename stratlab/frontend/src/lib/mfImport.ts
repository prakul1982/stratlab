/* The mutual fund import's summary line, a pure function (unit/review-dg1.test.mjs reads it). */

/** The import's line (DP2-017, DG-026): transactions and the stamp duty lines apart, and the schemes kept beside the file's. */
export function importLine(r: { added: number; duplicates: number; schemes: number; kept?: number; charges?: number }): string {
  const charges = r.charges ?? 0, txns = r.added - charges;
  const kept = r.kept ?? r.schemes;
  return `${txns} transaction${txns === 1 ? "" : "s"}${charges ? ` and ${charges} stamp duty or tax line${charges === 1 ? "" : "s"}` : ""} added`
    + (r.duplicates > 0 ? `, ${r.duplicates} already saved (skipped)` : "")
    + `, from ${kept === r.schemes ? `${r.schemes} scheme${r.schemes === 1 ? "" : "s"}` : `${kept} of the file's ${r.schemes} schemes`}.`;
}
