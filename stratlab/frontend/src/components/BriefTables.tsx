import { Link } from "react-router-dom";
import { safeHref } from "../lib/format";
import { inAppPath } from "../lib/investUi";
import type { BriefCell, BriefTable } from "../lib/news";
import { DataTable, type Column } from "./kit";

/* A brief's sections as tables (O5): the Briefs page draws what the server's tables.py made, the email and the PDF the same. A change
 * keeps its arrow and sign, a stock links to its page in the app, a headline's source is a column of its own. */

const TONE = { up: "k-up", down: "k-down", flat: "k-muted" } as const;

/** An address on this site opens in the app; anything else opens in a new tab. */
function Anchor({ href, children, ext }: { href?: string; children: string; ext?: boolean }) {
  const safe = safeHref(href);
  if (!safe) return <>{children}</>;
  const inApp = ext ? null : inAppPath(safe, window.location);
  if (inApp) return <Link className="link" to={inApp}>{children}</Link>;
  return <a className="link" href={safe} target="_blank" rel="noopener noreferrer">{children}{ext ? <span aria-hidden="true"> ↗</span> : null}</a>;
}

export function Cell({ c }: { c: BriefCell }) {
  if (typeof c === "string") return <>{c}</>;
  const text = c.t ?? "";
  const body = c.href && text ? <Anchor href={c.href} ext={c.ext}>{text}</Anchor> : text;
  return (
    <>
      {c.tone && text ? <span className={TONE[c.tone]}>{body}</span> : body}
      {c.sub && <span className="k-sub-line">{c.sub}</span>}
      {c.lines?.map((l, i) => <span key={i} className="k-sub-line">{l.href ? <Anchor href={l.href}>{l.t}</Anchor> : l.t}</span>)}
    </>
  );
}

/** The longest text in a column (its cells' main words and the lines under them). */
const longest = (rows: BriefCell[][], k: number): number => Math.max(0, ...rows.map((r) => {
  const c = r[k];
  if (c == null) return 0;
  if (typeof c === "string") return c.length;
  return Math.max((c.t ?? "").length, (c.sub ?? "").length, ...(c.lines ?? []).map((l) => l.t.length));
}));
/** site83 (owner, 20 Nov: no table wider than its box): a column of words takes a wrapping column's room (7rem at least) only when its words
 * are long enough to wrap; "Stage 2", "Up" and "18 Nov" in three such columns ran the brief's stock tables past its 460px column at 1280. */
const WRAP_FROM = 40;

export function BriefTables({ tables }: { tables: BriefTable[] }) {
  return (
    <>
      {tables.map((t, i) => (
        <section key={i} className="k-stack" data-testid="brief-section">
          <h3 className="k-sub">{t.title}</h3>
          {t.kind === "text" ? (
            <ul className="news-items">{t.items.map((it, j) => <li key={j}>{typeof it === "string" ? it : <Cell c={it} />}</li>)}</ul>
          ) : (
            <>
              <DataTable label={t.title} rows={t.rows} rowKey={(_, n) => `${i}-${n}`} stack
                columns={t.head.map((h, k): Column<BriefCell[]> => ({
                  key: `c${k}`, header: h, numeric: t.align[k] === "r", rowHeader: k === 0, wrap: t.align[k] === "l" && k > 0 && longest(t.rows, k) > WRAP_FROM, cell: (r) => <Cell c={r[k] ?? ""} />,
                }))} />
              {(t.note || t.link) && (
                <p className="k-note">{t.note}{t.note && t.link ? " " : ""}{t.link && <Anchor href={t.link.href}>{t.link.a}</Anchor>}</p>
              )}
            </>
          )}
        </section>
      ))}
    </>
  );
}
