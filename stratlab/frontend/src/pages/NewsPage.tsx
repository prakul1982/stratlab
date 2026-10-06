import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { safeHref } from "../lib/format";
import { dayName, NEWS_FOOTER, type Issue, type IssueRow } from "../lib/news";
import { AsOf, Loading } from "../components/ui";

type Tab = "IN" | "US" | "mine";
const TABS: [Tab, string][] = [["IN", "Market brief: India"], ["US", "Market brief: US"], ["mine", "My stocks"]];
const TAB_KEY = "stratlab.news.tab";
const isTab = (t: string | null): t is Tab => t === "IN" || t === "US" || t === "mine";
const listPath = (t: Tab) => (t === "mine" ? "/news?kind=my_stocks&limit=20" : `/news?kind=market&region=${t}&limit=20`);
const wide = () => typeof matchMedia === "function" && matchMedia("(min-width: 901px)").matches;

/** The newsletters, readable in the app: a list of issues per brief, and the one picked shown beside it. */
export function NewsPage() {
  const [params, setParams] = useSearchParams();
  const saved = (() => { try { return localStorage.getItem(TAB_KEY); } catch { return null; } })();
  const fromUrl = params.get("tab");
  const tab: Tab = isTab(fromUrl) ? fromUrl : isTab(saved) ? saved : "IN";
  const picked = params.get("issue");

  const [rows, setRows] = useState<IssueRow[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);

  const pick = useCallback((id: string | null, replace = false) => {
    setParams((p) => { const n = new URLSearchParams(p); if (id) n.set("issue", id); else n.delete("issue"); return n; }, { replace });
  }, [setParams]);
  const choose = (t: Tab) => {
    try { localStorage.setItem(TAB_KEY, t); } catch { /* storage off */ }
    setParams({ tab: t });
  };

  useEffect(() => {
    let live = true;
    setRows(null); setListError(null);
    api<{ issues?: IssueRow[] }>(listPath(tab))
      .then((r) => { if (live) setRows(Array.isArray(r?.issues) ? r.issues : []); })
      .catch((e: ApiError) => { if (!live) return; if (e.status === 404) setRows([]); else setListError(e.message || "Something went wrong."); });
    return () => { live = false; };
  }, [tab, tries]);

  // on a wide screen there's room for both, so open the latest issue straight away
  useEffect(() => { if (rows?.length && !picked && wide()) pick(rows[0].id, true); }, [rows, picked, pick]);

  return (
    <div className="stack" style={{ gap: 24 }}>
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Newsletters</span>
        <h1 className="page-title">News</h1>
        <p className="page-sub">A short brief after each market close, for India, the US and the companies you follow. Want it by email? Turn it on in <Link className="link" to="/settings#newsletters">Settings → Notifications</Link>.</p>
        <div className="seg" role="radiogroup" aria-label="Which brief" style={{ alignSelf: "flex-start", maxWidth: "100%" }}>
          {TABS.map(([t, title]) => <button key={t} role="radio" aria-checked={tab === t} aria-pressed={tab === t} onClick={() => choose(t)}>{title}</button>)}
        </div>
      </div>

      {listError ? (
        <div className="card dashed stack empty" style={{ gap: 12 }}>
          <h2 className="h2">Couldn't load the news</h2>
          <p className="muted">{listError} Check your connection and try again; your newsletter settings are safe.</p>
          <button className="btn outline" onClick={() => setTries((n) => n + 1)}>Try again</button>
        </div>
      ) : !rows ? <Loading label="Loading the issues" />
        : !rows.length ? (
          <div className="card dashed stack empty" style={{ gap: 14 }}>
            <p style={{ fontSize: 17 }}>No issues yet — the first one arrives after the next market close.</p>
            <Link to="/settings#newsletters" className="btn outline">Newsletter settings</Link>
          </div>
        ) : (
          <div className={`news-grid${picked ? " reading" : ""}`}>
            <nav className="news-list stack" style={{ gap: 2 }} aria-label="Issues">
              {rows.map((r) => (
                <button key={r.id} className="news-pick" aria-current={picked === r.id} onClick={() => pick(r.id)}>
                  <span className="row wrap" style={{ gap: 8 }}>
                    <span className="eyebrow">{dayName(r.day)}</span>
                    {r.weekly && <span className="badge next">Weekly</span>}
                  </span>
                  <b>{r.subject}</b>
                  {r.preview && <span className="small muted news-preview">{r.preview}</span>}
                </button>
              ))}
            </nav>
            <div className="stack" style={{ gap: 12, minWidth: 0 }}>
              {picked ? <>
                <button className="btn quiet sm news-back" style={{ alignSelf: "flex-start" }} onClick={() => pick(null)}>← All issues</button>
                <IssueView id={picked} />
              </> : <p className="muted news-hint">Pick an issue to read it.</p>}
            </div>
          </div>
        )}
    </div>
  );
}

function IssueView({ id }: { id: string }) {
  const [issue, setIssue] = useState<Issue | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setIssue(null); setError(null);
    api<Issue>(`/news/${encodeURIComponent(id)}`)
      .then((r) => { if (live) setIssue(r); })
      .catch((e: ApiError) => { if (live) setError(e.status === 404 ? "This issue isn't available any more." : e.message || "Something went wrong."); });
    return () => { live = false; };
  }, [id]);

  if (error) return <div className="card dashed"><p className="muted">{error}</p></div>;
  if (!issue) return <Loading label="Opening the issue" />;
  const label = issue.kind === "my_stocks" ? "My stocks" : `Market brief · ${issue.region === "US" ? "US" : "India"}`;
  return (
    <article className="card stack news-issue" style={{ gap: 18 }}>
      <div className="stack" style={{ gap: 8 }}>
        <span className="row wrap" style={{ gap: 8 }}>
          <span className="eyebrow">{label} · {dayName(issue.day, true)}</span>
          {issue.weekly && <span className="badge next">Weekly</span>}
        </span>
        <h2 className="serif" style={{ fontSize: "clamp(24px, 3vw, 32px)", fontWeight: 400, letterSpacing: "-0.01em", lineHeight: 1.2 }}>{issue.subject}</h2>
        <AsOf parts={[["Prices and numbers", issue.at]]} />
        {issue.summary && <p style={{ fontSize: 17 }}>{issue.summary}</p>}
      </div>
      {(issue.sections ?? []).filter((s) => s.items?.length).map((s, i) => (
        <section key={i} className="stack" style={{ gap: 8 }}>
          <h3 className="h2" style={{ fontSize: 18 }}>{s.title}</h3>
          <ul className="news-items">
            {s.items.map((it, j) => {
              const region = it.region ?? issue.region ?? "IN";
              return (
                <li key={j}>
                  <ItemText text={it.text} url={it.url} />
                  {it.symbol && <> <Link className="link" to={`/research/${region}/${encodeURIComponent(it.symbol)}`}>{it.symbol}</Link></>}
                  {!!it.lines?.length && <ul className="news-lines">{it.lines.map((l, k) => <li key={k}><ItemText text={l.text} url={l.url} /></li>)}</ul>}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      <p className="tiny muted" style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}>{NEWS_FOOTER}</p>
    </article>
  );
}


/** A line of an issue: links into StratLab open in the app; anything else opens the source in a new tab. */
function ItemText({ text, url }: { text: string; url?: string | null }) {
  const href = safeHref(url);
  if (!href) return <>{text}</>;
  const u = new URL(href, window.location.origin);
  if (u.origin === window.location.origin || /^\/(research|paper|news|account)\b/.test(href)) {
    return <Link className="link" to={u.pathname + u.search}>{text}</Link>;
  }
  return <>{text} <a className="link" href={href} target="_blank" rel="noopener noreferrer">Source ↗</a></>;
}
