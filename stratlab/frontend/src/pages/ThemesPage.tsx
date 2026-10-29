import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApp } from "../lib/app";
import { writtenAt, marketTz } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { THEME_IDEAS, researchApi, useRegion, type SectorAI } from "../lib/research";
import { themeApi, type Business, type Dive, type Listing, type NewsRow, type Prices } from "../lib/theme";
import { RegionSwitch } from "../components/Research";
import { ChainCard, ClaimsCard, LayerCard, ListingsCard, NewsCard, NumbersCards, SubThemesCard } from "../components/ThemeDive";
import { Card, CardHead, DataTable, ErrorState, Field, FormActions, FormGrid, Notice, PageHeader, PageNav, Skeleton } from "../components/kit";

/* ================= Themes: a theme deep dive =================
 * The map (who is in the theme, written by AI and checked company by company), then the numbers worked out from the figures the app already
 * holds: the whole chain in one table, margins by layer, the sub-themes' companies, the latest news and the theme as a whole. The AI writes
 * no figure; a company is shown only where its own description says it does the work. */
const PRICE_TRIES = 6;
const PRICE_EVERY_MS = 8000;

export function ThemesPage() {
  const [region, setRegion] = useRegion();
  const [params, setParams] = useSearchParams();
  const { me } = useApp();
  const q = params.get("q") ?? "";
  const [text, setText] = useState(q);
  const [r, setR] = useState<SectorAI | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dive, setDive] = useState<Dive | null>(null);
  const [diveError, setDiveError] = useState<string | null>(null);
  const [prices, setPrices] = useState<Prices | null>(null);
  const [pricesBusy, setPricesBusy] = useState(false);
  const [news, setNews] = useState<NewsRow[] | null>(null);
  const [newsBusy, setNewsBusy] = useState(false);
  const [biz, setBiz] = useState<Business | null>(null);
  const [ipos, setIpos] = useState<{ items: Listing[]; checked: boolean } | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const seq = useRef(0);   // a late answer for an earlier theme or market is ignored, and doesn't clear "Mapping…" for the newer one
  const run = async (theme: string, o: { refresh?: boolean; keep?: boolean } = {}) => {
    if (!theme.trim()) return;
    const mine = ++seq.current;
    setBusy(true); setError(null); if (!o.refresh && !o.keep) { setR(null); setDive(null); setPrices(null); setNews(null); setBiz(null); setIpos(null); }
    try { const out = await researchApi.sector(region, theme, !!o.refresh); if (mine === seq.current) setR(out); }
    catch (e) { if (mine === seq.current) setError((e as Error).message); }
    finally { if (mine === seq.current) setBusy(false); }
  };
  useEffect(() => {
    setText(q);
    if (q) run(q);
    else { seq.current++; setR(null); setError(null); setBusy(false); setDive(null); }
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [q, region]);

  // the numbers load beside the map: each card fills when its own read is in
  const key = r ? `${q}|${region}|${r.generated_at}|${r.placements?.placed ?? 0}|${r.placements?.pending ?? 0}` : "";
  useEffect(() => {
    if (!r || !q) return;
    let live = true;
    setDiveError(null); setDive(null);
    themeApi.dive(region, q).then((d) => live && setDive(d)).catch((e) => live && setDiveError((e as Error).message));
    setNewsBusy(true); themeApi.news(region, q).then((n) => live && setNews(n.items)).catch(() => live && setNews(null)).finally(() => live && setNewsBusy(false));
    themeApi.business(region, q).then((b) => live && setBiz(b)).catch(() => live && setBiz(null));
    themeApi.listings(region, q).then((l) => live && setIpos(l)).catch(() => live && setIpos({ items: [], checked: false }));
    return () => { live = false; };
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [key]);
  // prices: read at a gentle pace on the server; asked again while some companies are still waiting
  useEffect(() => {
    if (!dive || !q || dive.members === 0) { setPrices(null); return; }
    let live = true, tries = 0, timer: ReturnType<typeof setTimeout> | undefined;
    const go = () => {
      setPricesBusy(true);
      themeApi.prices(region, q).then((p) => {
        if (!live) return;
        setPrices(p); setPricesBusy(false);
        if (p.pending > 0 && ++tries < PRICE_TRIES) timer = setTimeout(go, PRICE_EVERY_MS);
      }).catch(() => { if (live) setPricesBusy(false); });
    };
    go();
    return () => { live = false; if (timer) clearTimeout(timer); };
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [dive]);

  const go = (t: string) => { if (!t.trim()) return; const p = new URLSearchParams(params); p.set("q", t); p.set("region", region); setParams(p); };
  const pending = (r?.placements?.pending ?? 0) > 0;
  const draftIt = async () => {
    setDraft("Drafting…");
    try { const d = await themeApi.draft(region, q); setDraft(d.result === "nothing notable" ? "The figures show nothing notable enough for a post yet." : d.slug ? `Draft saved (${d.result}). It is hidden: read it under Admin, Blog, and publish it there if it is right.` : `Not drafted: ${d.problem ?? d.result}.`); }
    catch (e) { setDraft((e as Error).message); }
  };
  const nav = dive ? [
    { id: "theme-chain", label: "The chain" }, ...(dive.layers.length ? [{ id: "layer-0", label: "Layers" }] : []), ...(dive.subs.length ? [{ id: "theme-subs", label: "Sub-themes" }] : []),
    { id: "theme-claims", label: "Tailwinds and risks" }, { id: "theme-news", label: "Latest" }, { id: "numbers-size", label: "The theme in numbers" }, { id: "numbers-leaders", label: "Every company" },
  ] : [];
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/themes")} title="Map a theme, find the companies in it"
        lede="Type a sector or trend. The AI maps who's involved along the chain; each company is kept only where its own description shows it does that work, and the margins, growth and prices beside it are worked out from reported figures." />
      <div className="k-toolbar"><RegionSwitch region={region} setRegion={setRegion} /></div>
      <Card>
        <FormGrid label="Map a theme" onSubmit={(e) => { e.preventDefault(); go(text); }}>
          <Field label="Theme" wide value={text} onChange={(e) => setText(e.target.value)} placeholder={region === "IN" ? "India defence, railways capex…" : "AI data centers, grid electrification…"} />
          <FormActions>
            <button className="btn" disabled={busy}>{busy ? "Mapping…" : "Map it"}</button>
            <span className="k-small k-muted">Or try</span>
            {THEME_IDEAS[region].map((t) => <button key={t} type="button" className="btn quiet sm" onClick={() => go(t)}>{t}</button>)}
          </FormActions>
        </FormGrid>
      </Card>
      {error && <ErrorState title="The theme couldn't be mapped" action={{ label: "Try again", onClick: () => run(q, { refresh: true }) }}>{error}</ErrorState>}
      {busy && !r && <Card><Skeleton label={`Mapping "${q}" and checking each company (takes about a minute the first time)`} lines={4} /></Card>}
      {r && (
        <>
          <Card>
            <CardHead title={r.sector} actions={<><span className="k-note">Written {writtenAt(r.generated_at, marketTz(region))}</span>
              <button className="btn quiet sm" disabled={busy} onClick={() => run(q, { refresh: true })}>{busy ? "Mapping…" : "Refresh"}</button></>} />
            <p className="k-lede">{r.summary}</p>
            {r.core && <p className="k-small">Everything converges on <b>{r.core}</b>.</p>}
            {r.etfs.length > 0 && (
              <DataTable label="Funds that track the theme" columns={[
                { key: "t", header: "Fund", rowHeader: true, cell: (e: (typeof r.etfs)[number]) => <Link className="link" to={`/research/${region}/${encodeURIComponent(e.ticker)}`}><b>{e.ticker}</b></Link> },
                { key: "n", header: "Name", wrap: true, cell: (e) => e.name }]} rows={r.etfs} rowKey={(e) => e.ticker} />
            )}
          </Card>
          {pending && (
            <Notice tone="warn" action={{ label: "Check again", onClick: () => run(q, { keep: true }) }}>
              {r.placements!.pending} compan{r.placements!.pending === 1 ? "y is" : "ies are"} still being checked against their own descriptions, so {r.placements!.pending === 1 ? "it isn't" : "they aren't"} shown yet.
            </Notice>
          )}
          {diveError && <ErrorState title="The theme's numbers couldn't be loaded" action={{ label: "Try again", onClick: () => run(q, { keep: true }) }}>{diveError}</ErrorState>}
          {!dive && !diveError && <Card><Skeleton label="Working out the theme's figures" lines={5} /></Card>}
          {dive && (
            <>
              {nav.length > 1 && <PageNav items={nav} />}
              {me?.is_admin && dive.notable.length > 0 && (
                <Notice action={{ label: "Draft a blog post", onClick: draftIt }}>{draft ?? "The figures show something notable. A draft post can be made from them; it stays hidden until you publish it."}</Notice>
              )}
              {dive.members === 0 ? (
                <Card><p className="k-small">No listed company could be placed in this theme: none of the companies the map named has a description that shows it does the work. Try a more specific theme.</p></Card>
              ) : <ChainCard dive={dive} />}
              {biz && !biz.allowed && dive.region === "IN" && <p className="k-note">Operating figures that companies file between results (monthly sales, output, traffic) are on the Basic plan.</p>}
              {dive.layers.map((l, i) => <LayerCard key={l.layer} layer={l} i={i} region={dive.region} business={biz?.layers[i]?.rows} />)}
              <SubThemesCard dive={dive} business={biz} />
            </>
          )}
          <ClaimsCard tailwinds={r.tailwinds} risks={r.risks} />
          {dive && <NewsCard items={news} loading={newsBusy} />}
          {dive && dive.members > 0 && (
            <>
              <h2 className="k-section-title" id="theme-numbers">The theme in numbers</h2>
              <p className="k-note">Reported figures from each company's stored page{dive.as_of ? `, prices to ${dive.as_of}` : ""}; the sections below say what each is on.</p>
              <NumbersCards dive={dive} prices={prices} pricesBusy={pricesBusy} />
              <ListingsCard items={ipos && ipos.checked ? ipos.items : null} checked={ipos?.checked ?? true} region={dive.region} />
            </>
          )}
          {r.exchange && r.exchange.companies.length > 0 && (
            <Card>
              <CardHead title="On the exchange's list for these industries" info="Every listed company the exchange classifies under the same industries as the checked companies, A to Z. It is a list by industry, not a claim that each does the work of a layer." />
              <p className="k-small k-muted">{r.exchange.industries.join(" · ")}: {r.exchange.total.toLocaleString("en-IN")} compan{r.exchange.total === 1 ? "y" : "ies"}{r.exchange.total > r.exchange.companies.length ? `, the first ${r.exchange.companies.length} A to Z` : ""}.</p>
              <DataTable label="Listed companies in the same industries" columns={[
                { key: "n", header: "Company", rowHeader: true, wrap: true, cell: (c: NonNullable<SectorAI["exchange"]>["companies"][number]) => <Link className="link" to={`/research/${region}/${encodeURIComponent(c.ticker)}`}><b>{c.name}</b></Link> },
                { key: "t", header: "Symbol", cell: (c) => c.ticker }, { key: "i", header: "Industry", wrap: true, cell: (c) => c.industry },
                { key: "m", header: "Shown above", cell: (c) => (c.named ? "Yes" : "No") }]} rows={r.exchange.companies} rowKey={(c) => c.ticker} />
            </Card>
          )}
          <p className="k-note">The text on this page that describes how a layer or sub-theme works is written by AI from general knowledge, with no figures. Every company sits only where its own description shows it does that work, with the words from it shown. Every figure is from the companies' reported numbers or stored pages, with its year and basis.</p>
        </>
      )}
    </div>
  );
}
