import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { eyebrowOf } from "../lib/eyebrow";
import { fmtDate, safeHref } from "../lib/format";
import { download as saveFile } from "../lib/share";
import { RegionSwitch } from "../components/Research";
import { apiPath, lockedFilters, planLine, readQuery, snippetParts, totalLine, whereLine, writeQuery,
  type DocAnswer, type DocHit, type DocQuery, type DocRegion, type DocStatus } from "../lib/docSearch";
import { Badge, Card, CardHead, ChipSet, DateField, EmptyState, ErrorState, Field, FieldGroup, FormActions, FormGrid, PageHeader, Pager,
  PlanNote, Skeleton, StockPicker, Suggest, type SuggestItem } from "../components/kit";
import "./docsearch.css";

/* Search inside filings and call transcripts: words or a phrase found in the companies' own documents (NIFTY 500 call
 * transcripts and investor presentations, S&P 500 annual reports and earnings releases), each hit a short extract with the
 * match marked and a link to the filed copy at its page. Signed-in only; the plan decides how many hits and which filters
 * (backend plans.DOC_SEARCH). Facts only: the companies' own words, in date or match order, never ranked as good or bad. */

const EXAMPLES = ["order book", "capacity utilisation", "\"price hike\"", "capex guidance"];

/** One extract, its matched words marked: text nodes only (snippetParts), never HTML from a document. */
function Extract({ html }: { html: string }) {
  return <p className="ds-extract">{snippetParts(html).map((p, i) => (p.hit ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>))}</p>;
}

function Hit({ h }: { h: DocHit }) {
  return (
    <li className="ds-hit" data-hit={h.id}>
      <div className="ds-hit-head">
        <Link className="link ds-co" to={`/research/${h.region}/${encodeURIComponent(h.symbol)}`}><b>{h.company}</b></Link>
        <span className="k-small k-muted">{h.symbol} · {h.kind_label} · filed {fmtDate(h.filed_at)}</span>
      </div>
      <span className="k-small ds-title">{h.title}</span>
      <blockquote className="ds-quote" aria-label={`Extract from ${h.company}'s ${h.kind_label.toLowerCase()}`}>
        {h.snippet.map((s, i) => <Extract key={i} html={s} />)}
      </blockquote>
      <div className="k-row tight ds-hit-foot">
        {h.url ? <a className="link k-small" href={safeHref(h.url)} target="_blank" rel="noopener noreferrer">
          {h.page ? `Open at page ${h.page}` : "Open the filed copy"} ↗<span className="sr-only"> ({h.company}, {h.title}, opens in a new tab)</span></a> : null}
        <span className="k-small k-muted">{whereLine(h)}</span>
        {h.ocr && <Badge tone="plain" dot={false}>Read from a scan</Badge>}
      </div>
    </li>
  );
}

const themeNames = (region: DocRegion) => async (q: string): Promise<SuggestItem[]> => {
  const r = await api<{ items: { name: string; q: string; members?: number }[] }>(`/theme-library/suggest?region=${region}&q=${encodeURIComponent(q)}`);
  return r.items.map((t) => ({ key: t.q, label: t.name, note: t.members ? `${t.members} companies` : undefined }));
};

export function DocSearchPage() {
  const { me, notify, fail } = useApp();
  const [params, setParams] = useSearchParams();
  const query = useMemo(() => readQuery(params), [params]);
  const [draft, setDraft] = useState<DocQuery>(query);
  const [status, setStatus] = useState<DocStatus | null>(null);
  const [ans, setAns] = useState<DocAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const [getting, setGetting] = useState(false);
  const filters = status?.limits.filters ?? me?.plan_info.features?.doc_search ?? false;
  const canExport = status?.limits.export ?? me?.plan_info.features?.doc_search_all ?? false;
  const dropped = filters ? [] : lockedFilters(query);

  useEffect(() => { setDraft(query); }, [query]);
  useEffect(() => {
    let live = true;
    api<DocStatus>("/research/docs/status").then((s) => live && setStatus(s)).catch(() => undefined);
    return () => { live = false; };
  }, []);
  useEffect(() => {
    if (!query.q.trim() || !me) { setAns(null); return; }
    let live = true;
    setBusy(true); setError(null);
    api<DocAnswer>(apiPath(query, filters))
      .then((a) => live && setAns(a))
      .catch((e) => { if (live) { setAns(null); setError((e as ApiError).message); } })
      .finally(() => live && setBusy(false));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, tries, filters, !!me]);

  const go = (d: DocQuery) => setParams(writeQuery(d));
  const submit = (e: React.FormEvent) => { e.preventDefault(); if (draft.q.trim()) go({ ...draft, page: 1 }); };
  const set = <K extends keyof DocQuery>(k: K, v: DocQuery[K]) => setDraft((d) => ({ ...d, [k]: v }));
  const toggle = (k: "sectors" | "kinds", v: string) => setDraft((d) => ({ ...d, [k]: d[k].includes(v) ? d[k].filter((x) => x !== v) : [...d[k], v] }));
  const setRegion = (r: DocRegion) => go({ ...draft, region: r, symbols: [], sectors: [], kinds: [], theme: "", page: 1 });
  const csv = async () => {
    setGetting(true);
    try {
      const r = await api<Response>(apiPath(query, true, "/research/docs/export"), { raw: true });
      saveFile(await r.blob(), `stratlab-filings-${query.q.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 40) || "search"}.csv`);
      notify("Downloaded the results as a CSV.");
    } catch (e) { fail(e); } finally { setGetting(false); }
  };

  const cov = status?.coverage[query.region];
  const kinds = status?.kinds[query.region] ?? [];
  const sectors = status?.sectors[query.region] ?? [];
  const covers = status?.covers[query.region];
  const info = covers ? <>{covers}{cov ? ` Read so far: ${cov.documents.toLocaleString("en-IN")} documents of ${cov.companies.toLocaleString("en-IN")} companies${cov.newest ? `, the newest filed ${fmtDate(cov.newest)}` : ""}.` : ""} {status?.note}</> : undefined;

  return (
    <div className="k-page ds-page">
      <PageHeader eyebrow={eyebrowOf("/research/search")} title="Search filings"
        lede="Find words and phrases inside companies' call transcripts, investor presentations, annual reports and earnings releases. Each result is a short extract in the company's own words, linked to the filed copy."
        info={info} infoLabel="What is searched" />
      <div className="k-toolbar"><RegionSwitch region={query.region} setRegion={setRegion} /></div>

      <Card label="Search the documents">
        <FormGrid label="Search the documents" onSubmit={submit}>
          <Field label="Words or a phrase" wide value={draft.q} placeholder={'Like "order book" or capacity utilisation'} maxLength={200}
            onChange={(e) => set("q", e.target.value)} hint={'Quotes find the exact phrase; -word leaves a word out; "or" finds either word.'} />
          <FieldGroup label="Companies">
            <div className="k-stack tight">
              <StockPicker market={query.region} clearOnPick listedOnly placeholder={query.region === "US" ? "Like AAPL or Apple" : "Like RELIANCE or Infosys"}
                onPick={(s) => setDraft((d) => (d.symbols.includes(s) || d.symbols.length >= 20 ? d : { ...d, symbols: [...d.symbols, s] }))} />
              {draft.symbols.length > 0 && (
                <div className="k-row tight" aria-label="Companies searched">
                  {draft.symbols.map((s) => <button key={s} type="button" className="chip" onClick={() => set("symbols", draft.symbols.filter((x) => x !== s))}
                    aria-label={`Remove ${s}`}>{s} <span aria-hidden="true">×</span></button>)}
                </div>
              )}
            </div>
          </FieldGroup>
          {filters && kinds.length > 0 && (
            <FieldGroup label="Kind of document">
              <ChipSet label="Kind of document" options={kinds.map((k) => ({ value: k.id, label: k.label }))} on={draft.kinds} onToggle={(v) => toggle("kinds", v)} />
            </FieldGroup>
          )}
          {filters && sectors.length > 0 && (
            <FieldGroup label="Sector">
              <ChipSet label="Sector" options={sectors.map((s) => ({ value: s, label: s }))} on={draft.sectors} onToggle={(v) => toggle("sectors", v)} />
            </FieldGroup>
          )}
          {filters && (
            <Field label="Theme" optional info="The companies of a theme already mapped in Themes.">
              {(id) => <Suggest id={id} value={draft.theme} minChars={2} placeholder="Like defence or semiconductors" load={themeNames(query.region)}
                onText={(t) => set("theme", t)} onPick={(t) => set("theme", t.key)} empty="No mapped theme by that name." />}
            </Field>
          )}
          {filters && <DateField label="Filed from" optional value={draft.from} onChange={(v) => set("from", v)} max={draft.to || undefined} />}
          {filters && <DateField label="Filed to" optional value={draft.to} onChange={(v) => set("to", v)} min={draft.from || undefined} />}
          <FormActions>
            <button className="btn" type="submit" disabled={!draft.q.trim()}>Search</button>
            {(draft.symbols.length > 0 || draft.kinds.length > 0 || draft.sectors.length > 0 || draft.theme || draft.from || draft.to) && (
              <button className="btn quiet" type="button" onClick={() => setDraft((d) => ({ ...d, symbols: [], kinds: [], sectors: [], theme: "", from: "", to: "" }))}>Clear filters</button>
            )}
          </FormActions>
        </FormGrid>
        {!filters && me && <PlanNote>Filters by sector, theme, kind of document and date, and every result, are on the Basic plan. Free searches by company and shows the first 3 results.</PlanNote>}
        {dropped.length > 0 && <p className="k-small k-muted" role="status">Searched without the {dropped.join(", ")} filter{dropped.length > 1 ? "s" : ""}: filters beyond the company are on the Basic plan.</p>}
      </Card>

      <Card label="Results" id="results">
        {!query.q.trim() ? (
          <EmptyState title="Search inside the filed documents">
            Type a word or a phrase above. Try:{" "}
            {EXAMPLES.map((x, i) => <span key={x}>{i > 0 && ", "}<button type="button" className="link-btn" onClick={() => go({ ...draft, q: x, page: 1 })}>{x}</button></span>)}.
          </EmptyState>
        ) : error ? (
          <ErrorState title="The search didn't work" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState>
        ) : busy && !ans ? (
          <Skeleton label="Searching the documents" lines={5} />
        ) : !ans ? null : !ans.ready ? (
          <EmptyState title="The documents aren't searchable yet">The search index is being set up. Documents are read each night; try again later.</EmptyState>
        ) : ans.total === 0 ? (
          <EmptyState title={`No document mentions “${ans.q}”`}>
            {ans.symbols.length || ans.theme || ans.kinds.length || ans.sectors.length ? "Try without some of the filters, or other words." : "Try other words, or fewer of them."}
            {ans.floor ? ` Documents filed since ${fmtDate(ans.floor)} were searched.` : ""}
          </EmptyState>
        ) : (
          <>
            <CardHead title={`${totalLine(ans.total, ans.more)} mention “${ans.q}”`}
              actions={canExport ? <button type="button" className="btn quiet sm" onClick={csv} disabled={getting}>{getting ? "Downloading…" : "Download CSV"}</button> : undefined} />
            <p className="k-small k-muted ds-sub" aria-live="polite">
              {ans.by_date ? "So many documents match that they're shown newest first; add words or a filter to narrow them." : "Best matches first."}
              {ans.floor ? ` Filed since ${fmtDate(ans.floor)}.` : ""}
              {Object.keys(ans.facets.kinds).length > 1 ? ` ${Object.entries(ans.facets.kinds).map(([k, n]) => `${n} ${kinds.find((x) => x.id === k)?.label.toLowerCase() ?? k}${n === 1 ? "" : "s"}`).join(", ")}.` : ""}
            </p>
            <ol className="ds-hits" aria-label={`Results for ${ans.q}`}>{ans.hits.map((h) => <Hit key={h.id} h={h} />)}</ol>
            {ans.locked > 0 && <PlanNote>Free shows the first {ans.hits.length} of the {totalLine(ans.total, ans.more).toLowerCase()} found. Every result, with filters by sector, theme, kind of document and date, is on the Basic plan.</PlanNote>}
            <Pager page={ans.page} pages={ans.pages} total={ans.total} noun="documents" onPage={(n) => { go({ ...query, page: n }); document.getElementById("results")?.scrollIntoView({ block: "start" }); }} />
          </>
        )}
        {ans?.ready && <p className="k-note">{ans.note} {planLine(ans.limits)}</p>}
      </Card>
    </div>
  );
}
