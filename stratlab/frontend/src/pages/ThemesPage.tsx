import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApp } from "../lib/app";
import { writtenAt, marketTz } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { THEME_IDEAS, researchApi, useRegion, type SectorAI } from "../lib/research";
import { themeApi, type Business, type Dive, type Listing, type NewsRow, type Prices } from "../lib/theme";
import { RegionSwitch } from "../components/Research";
import { ChainCard, ClaimsCard, LayerCard, ListingsCard, MembersCard, NewsCard, NumbersCards, SubThemesCard, ThemeDownloads } from "../components/ThemeDive";
import { Card, CardHead, DataTable, ErrorState, Field, FormActions, FormGrid, Notice, PageHeader, PageNav, Skeleton, Working } from "../components/kit";

/* ================= Themes: a theme deep dive =================
 * Who is in the theme: every company the exchange classifies in its official industries, sorted into layers by AI, with the AI's additions
 * from other industries checked company by company (THEMES); then the numbers worked out from the figures the app already
 * holds: the whole chain in one table, margins by layer, the sub-themes' companies, the latest news and the theme as a whole. The AI writes
 * no figure; a company is shown only where its own description says it does the work. */
const PRICE_TRIES = 6;
const PRICE_EVERY_MS = 8000;
// a map whose AI parts are still being written behind it is asked again on its own, every 5 s for 90 s, then the page stops asking
// (THEMES item 6; LIVE3-001: the base shows at once, the AI's layers, explanations and checks fill in after)
const CHECK_TRIES = 18;
const CHECK_EVERY_MS = 5000;

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
    if (o.refresh) { tries.current = 0; setStopped(false); }   // Refresh asks again from the start
    if (!o.keep) setBusy(true);           // a quiet re-ask while the AI fills in doesn't turn the buttons to "Mapping…" every 5 s
    setError(null); if (!o.refresh && !o.keep) { setR(null); setDive(null); setPrices(null); setNews(null); setBiz(null); setIpos(null); }
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
    // the shown numbers stay while the theme is read again (owner, 7 Nov: "it was vanishing all the data for a sec and then bringing it
    // all back"); a new theme or market clears them in run()
    setDiveError(null);
    themeApi.dive(region, q).then((d) => live && setDive(d)).catch((e) => live && setDiveError((e as Error).message));
    setNewsBusy(true); themeApi.news(region, q).then((n) => live && setNews(n.items)).catch(() => live && setNews(null)).finally(() => live && setNewsBusy(false));
    themeApi.business(region, q).then((b) => live && setBiz(b)).catch(() => live && setBiz(null));
    themeApi.listings(region, q).then((l) => live && setIpos(l)).catch(() => live && setIpos({ items: [], checked: false }));
    return () => { live = false; setNewsBusy(false); };
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [key]);
  // prices: read at a gentle pace on the server; asked again while some companies are still waiting
  useEffect(() => {
    if (!dive || !q || dive.members === 0) { setPrices(null); setPricesBusy(false); return; }
    let live = true, tries = 0, timer: ReturnType<typeof setTimeout> | undefined;
    // busy while a read is out or another is coming: the bar stops when the page stops asking, even with some prices still not read
    // (owner, 7 Nov: "after finishing it's still loading")
    const go = () => {
      setPricesBusy(true);
      themeApi.prices(region, q).then((p) => {
        if (!live) return;
        setPrices(p);
        if (p.pending > 0 && ++tries < PRICE_TRIES) timer = setTimeout(go, PRICE_EVERY_MS);
        else setPricesBusy(false);
      }).catch(() => { if (live) setPricesBusy(false); });
    };
    go();
    return () => { live = false; if (timer) clearTimeout(timer); setPricesBusy(false); };
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [dive]);

  const go = (t: string) => { if (!t.trim()) return; const p = new URLSearchParams(params); p.set("q", t); p.set("region", region); setParams(p); };
  const pl = r?.placements;
  const working = r?.ai?.state === "working";
  const pending = working || (!!pl && !pl.checked && (pl.pending > 0 || pl.industries_by === "pending"));
  const tries = useRef(0);
  const [stopped, setStopped] = useState(false);       // the page asked CHECK_TRIES times and stopped: no bar that never ends
  useEffect(() => { tries.current = 0; setStopped(false); }, [q, region]);
  useEffect(() => {
    if (!pending) return;
    if (tries.current >= CHECK_TRIES) { setStopped(true); return; }
    const t = setTimeout(() => { tries.current++; run(q, { keep: true }); }, CHECK_EVERY_MS);
    return () => clearTimeout(t);
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [pending, r]);
  const draftIt = async () => {
    setDraft("Drafting…");
    try { const d = await themeApi.draft(region, q); setDraft(d.result === "nothing notable" || d.result === "too few figures" ? "The theme needs two layers with margin figures for a post." : d.slug ? `Draft saved (${d.result}). It is hidden: read it under Admin, Blog, and publish it there if it is right.` : `Not drafted: ${d.problem ?? d.result}.`); }
    catch (e) { setDraft((e as Error).message); }
  };
  const nav = dive ? [
    { id: "theme-members", label: "Companies" }, { id: "theme-chain", label: "The chain" }, ...(dive.layers.length ? [{ id: "layer-0", label: "Layers" }] : []), ...(dive.subs.length ? [{ id: "theme-subs", label: "Sub-themes" }] : []),
    { id: "theme-claims", label: "Tailwinds and risks" }, { id: "theme-news", label: "Latest" }, { id: "numbers-size", label: "The theme in numbers" }, { id: "numbers-leaders", label: "Every company" },
  ] : [];
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/themes")} title="Map a theme, find the companies in it"
        lede="Type a sector or trend. Every listed company the exchange classifies in its industries is in it; the AI maps them along the chain and adds companies from other industries, each checked against its own description. The margins, growth and prices beside them are worked out from reported figures." />
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
      {busy && !r && <Card><Skeleton label={`Mapping "${q}"`} lines={4} /></Card>}
      {r && (
        <>
          <Card>
            <CardHead title={r.sector} actions={<>{r.generated_at > 0 && <span className="k-note">Written {writtenAt(r.generated_at, marketTz(region))}</span>}
              <button className="btn quiet sm" disabled={busy} onClick={() => run(q, { refresh: true })}>{busy ? "Mapping…" : "Refresh"}</button></>} />
            {r.summary && <p className="k-lede">{r.summary}</p>}
            {r.core && <p className="k-small">Everything converges on <b>{r.core}</b>.</p>}
            <ThemeDownloads r={r} dive={dive} region={region} theme={q} />
            {r.etfs.length > 0 && (
              <DataTable label="Funds that track the theme" columns={[
                { key: "t", header: "Fund", rowHeader: true, cell: (e: (typeof r.etfs)[number]) => <Link className="link" to={`/research/${region}/${encodeURIComponent(e.ticker)}`}><b>{e.ticker}</b></Link> },
                { key: "n", header: "Name", wrap: true, cell: (e) => e.name }]} rows={r.etfs} rowKey={(e) => e.ticker} />
            )}
          </Card>
          {/* still being prepared: a moving bar and one short line; the page asks again on its own (owner, 5 Nov: no warnings for work in progress) */}
          {pending && stopped && <p className="k-note" data-testid="theme-still-checking">Some of this theme's checks are still running. Refresh to see them.</p>}
          {pending && !stopped && (
            <Working label={working && !r.generated_at ? "Mapping the theme: sorting its companies into layers. It fills in here on its own, usually within a minute."
              : pl && pl.pending > 0 ? "Checking each company against its own description…"
              : working ? "Writing the tailwinds and risks…"
              : "Picking the theme's industries…"} />
          )}
          {r.ai?.state === "failed" && (
            <Notice tone="warn" action={{ label: "Try again", onClick: () => run(q, { keep: true }) }}>
              The theme's layers couldn't be finished just now. The companies below are the exchange's own classification.
            </Notice>
          )}
          <MembersCard r={r} region={region} />
          {diveError && <ErrorState title="The theme's numbers couldn't be loaded" action={{ label: "Try again", onClick: () => run(q, { keep: true }) }}>{diveError}</ErrorState>}
          {!dive && !diveError && <Card><Skeleton label="Working out the theme's figures" lines={5} /></Card>}
          {dive && (
            <>
              {nav.length > 1 && <PageNav items={nav} />}
              {/* on every theme with figures (owner, 7 Nov: "did you remove the blog button for me too?": it showed only when the figures were notable) */}
              {me?.is_admin && dive.members > 0 && (
                <Notice action={{ label: "Draft a blog post", onClick: draftIt }}>{draft ?? (dive.notable.length > 0
                  ? "The figures show something notable. A draft post can be made from them; it stays hidden until you publish it."
                  : "A draft post can be made from this theme's figures; it stays hidden until you publish it.")}</Notice>
              )}
              {dive.members === 0 ? (
                <Card><p className="k-small">No company in this theme has stored figures yet: none is in an official industry of the theme, and none the map named has a description that shows it does the work. Try a more specific theme.</p></Card>
              ) : <ChainCard dive={dive} />}
              {dive.figures && dive.figures.of > dive.figures.shown && <p className="k-note">The figures below are for {dive.figures.shown} of the theme's {dive.figures.of.toLocaleString("en-IN")} companies: every one the map names, then the largest of the rest by market value.</p>}
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
          <p className="k-note">The text on this page that describes how a layer or sub-theme works is written by AI from general knowledge, with no figures. Every company of the theme's official industries is listed, whatever the AI says; a company the AI added from another industry is kept only while its own description doesn't show otherwise, with its words shown where they confirm the work. Every figure is from the companies' reported numbers or stored pages, with its year and basis.</p>
        </>
      )}
    </div>
  );
}
