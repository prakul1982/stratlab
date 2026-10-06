/** Previous and next under a long list that comes a page at a time: "Page 2 of 5 · 112 filings". Hidden when everything fits
 * on one page. `noun` is the plural word for the rows ("filings", "stocks"). */
export function Pager({ page, pages, total, noun = "results", onPage }: { page: number; pages: number; total: number; noun?: string; onPage: (page: number) => void }) {
  if (pages <= 1) return null;
  return (
    <nav className="k-pager" aria-label="Pages">
      <button type="button" className="btn quiet sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>← Previous</button>
      <span className="k-small k-muted" aria-live="polite">Page {page} of {pages} · {total.toLocaleString("en-IN")} {noun}</span>
      <button type="button" className="btn quiet sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next →</button>
    </nav>
  );
}
