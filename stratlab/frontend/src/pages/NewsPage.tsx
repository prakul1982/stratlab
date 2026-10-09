import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { asOf, marketTz, safeHref } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { dayName, NEWS_FOOTER, type Issue, type IssueRow } from "../lib/news";
import { Badge, Card, EmptyState, ErrorState, PageHeader, Seg, Skeleton } from "../components/kit";

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
  const choose = (t: string) => {
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
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/news")} title="Briefs"
        lede={<>A short brief after each market close, for India, the US and the companies you follow. Want it by email? Turn it on in <Link className="link" to="/settings#newsletters">Settings → Notifications</Link>.</>} />
      <div className="k-toolbar">
        <Seg label="Which brief" value={tab} onChange={choose} options={TABS.map(([t, title]) => ({ value: t, label: title }))} />
      </div>

      {listError ? (
        <Card><ErrorState title="Couldn't load the news" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{listError} Check your connection and try again; your newsletter settings are safe.</ErrorState></Card>
      ) : !rows ? <Card><Skeleton label="Loading the issues" lines={4} /></Card>
        : !rows.length ? (
          <Card><EmptyState title="No briefs yet" action={{ label: "Brief emails", to: "/settings#newsletters" }}>The first one arrives after the next market close. The headlines on each company's page are separate: they come in through the day.</EmptyState></Card>
        ) : (
          <div className={`news-grid${picked ? " reading" : ""}`}>
            <nav className="news-list inv-issues" aria-label="Issues">
              {rows.map((r) => (
                <button key={r.id} className="news-pick" aria-current={picked === r.id} onClick={() => pick(r.id)}>
                  <span className="k-row">
                    <span className="k-eyebrow">{dayName(r.day)}</span>
                    {r.weekly && <Badge tone="ok" dot={false}>Weekly</Badge>}
                  </span>
                  <b>{r.subject}</b>
                  {r.preview && <span className="k-small k-muted news-preview">{r.preview}</span>}
                </button>
              ))}
            </nav>
            <div className="k-stack">
              {picked ? <>
                <button className="btn quiet sm news-back k-btn-end" onClick={() => pick(null)}>← All issues</button>
                <IssueView id={picked} />
              </> : <p className="k-muted news-hint">Pick an issue to read it.</p>}
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

  if (error) return <Card><ErrorState title="This issue couldn't be opened">{error}</ErrorState></Card>;
  if (!issue) return <Card><Skeleton label="Opening the issue" lines={5} /></Card>;
  const label = issue.kind === "my_stocks" ? "My stocks" : `Market brief · ${issue.region === "US" ? "US" : "India"}`;
  return (
    <div className="news-issue">
      <Card label={issue.subject}>
        <div className="k-stack">
          <span className="k-row">
            <span className="k-eyebrow">{label} · {dayName(issue.day, true)}</span>
            {issue.weekly && <Badge tone="ok" dot={false}>Weekly</Badge>}
          </span>
          <h2 className="k-card-title">{issue.subject}</h2>
          {asOf(issue.at) && <span className="k-note">Prices and numbers as of {asOf(issue.at, { tz: marketTz(issue.region) })}</span>}
          {issue.summary && <p className="k-lede">{issue.summary}</p>}
          {issue.ai_summary && <p data-testid="news-ai-summary">{issue.ai_summary}</p>}
        </div>
        {(issue.sections ?? []).filter((s) => s.items?.length).map((s, i) => (
          <section key={i} className="k-stack">
            <h3 className="k-sub">{s.title}</h3>
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
        <p className="k-note">{NEWS_FOOTER}</p>
      </Card>
    </div>
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
