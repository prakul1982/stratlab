import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApp } from "../lib/app";
import { fmtDate, marketTz, writtenAt } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { THEME_IDEAS, researchApi, useRegion, type SectorAI } from "../lib/research";
import { bizFor, DIVE_UPDATING, LIBRARY_HEAD, libraryLabel, mapStamp, olderNote, shortTheme, themeApi, type Business, type Dive, type LibraryTheme, type Listing, type NewsRow, type Prices } from "../lib/theme";
import { StoredNote, StoredStamp, useStoredRefresh } from "../components/StoredStamp";
import { RegionSwitch } from "../components/Research";
import { ShareResearchButton } from "../components/ShareResearch";
import { ThemeLinksCard } from "../components/ThemeLinks";
import { ChainCard, ClaimsCard, LayerCard, ListingsCard, MembersCard, NewsCard, NumbersCards, SubThemesCard, ThemeDownloads } from "../components/ThemeDive";
import { ChangesCard } from "../components/ThemeChanges";
import { SaveButton, SavedList } from "../components/SavedSearches";
import { themeReady, themeSnap } from "../lib/savedSnap";
import { Card, CardHead, CardNote, DataTable, ErrorState, Notice, PageHeader, PageNav, Skeleton, Working } from "../components/kit";
import { watchSize } from "../lib/resize";
import { foreignTheme, ideasBeside, sameByName, twinNames, type Market } from "../lib/themeMarket";
import { emptyLayerLines, fundName, themeFunds } from "../lib/themeFormat";

/* ================= Themes: a theme deep dive =================
 * Who is in the theme: every company the exchange classifies in its official industries, sorted into layers by AI, with the AI's additions
 * from other industries checked company by company (THEMES); then the numbers worked out from the figures the app already
 * holds: the whole chain in one table, margins by layer, the sub-themes' companies, the latest news and the theme as a whole. The AI writes
 * no figure; a company is shown only where its own description says it does the work. */
const PRICE_TRIES = 6;
/** "the layer Small finance banks" / "the layers A, B and C" (LIVE9A-022). */
export const emptyNames = (names: string[]): string => `the ${names.length === 1 ? "layer" : "layers"} ${names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`}`;
const PRICE_EVERY_MS = 8000;
const LISTING_TRIES = 8;
const DIVE_TRIES = 6;              // LIVE10A-008: asks for a dive being read again behind the page, 20 s apart
const DIVE_EVERY_MS = 20_000;
// a map whose AI parts are still being written behind it is asked again on its own, every 5 s for 90 s, then the page stops asking
// (THEMES item 6; LIVE3-001: the base shows at once, the AI's layers, explanations and checks fill in after)
const CHECK_TRIES = 18;
const CHECK_EVERY_MS = 5000;
// r66e (LIVE12A-002): a theme served from its read under an earlier version of the checks is asked for again, gently, while it is checked again
const OLDER_TRIES = 12;
const OLDER_EVERY_MS = 30_000;

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
  const [ipos, setIpos] = useState<{ items: Listing[]; checked: boolean; pending?: boolean } | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const seq = useRef(0);   // a late answer for an earlier theme or market is ignored, and doesn't clear "Mapping…" for the newer one
  const rf = useStoredRefresh();
  const refreshed = useRef(false);  // after a Refresh, the figures are worked out again too (the company figures other themes share)
  const refresh = () => {
    const mine = ++seq.current;
    tries.current = 0; setStopped(false); refreshed.current = true;
    rf.run(async () => { const out = await researchApi.sector(region, q, true); if (mine === seq.current) setR(out); return out; });
  };
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
    // site87: an old link to one market's country-named theme under the other market is never mapped there (the API refuses it too)
    if (q && foreignTheme(q, region)) { seq.current++; setR(null); setBusy(false); setDive(null); setError(`“${q}” is a theme of ${region === "US" ? "India" : "the US"}, so it isn't mapped in ${region === "US" ? "the US" : "India"}. Pick a theme of this market.`); return; }
    if (q) run(q);
    else { seq.current++; setR(null); setError(null); setBusy(false); setDive(null); }
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [q, region]);
  // site87 (owner: India's "India defence" open, then "$ United States" mapped "India defence" in the US): a market switch closes the open
  // theme back to the chooser, then opens the other market's own theme of the same name only if its library has one ("Defence" →
  // "Aerospace and defense"); never one naming the other country
  const at = useRef(region);
  at.current = region;
  const switchMarket = (to: Market) => {
    if (to === region) return;
    const open = q;
    setText("");
    setRegion(to, (p) => p.delete("q"));
    if (!open) return;
    void (async () => {
      for (const name of twinNames(open, to)) {
        try {
          const hit = sameByName((await themeApi.suggest(to, name)).items, name);
          if (!hit || at.current !== to || foreignTheme(hit.name, to)) continue;
          const p = new URLSearchParams(window.location.search);
          if (p.get("q")) return;                 // the reader has picked a theme meanwhile
          p.set("region", to); p.set("q", hit.name); setParams(p, { replace: true });
          return;
        } catch { /* the library couldn't be read: stay on the chooser */ }
      }
    })();
  };

  // the numbers load beside the map: each card fills when its own read is in
  const key = r ? `${q}|${region}|${r.generated_at}|${r.placements?.placed ?? 0}|${r.placements?.pending ?? 0}|${r.older ? "older" : ""}` : "";
  useEffect(() => {
    if (!r || !q) return;
    let live = true;
    // the shown numbers stay while the theme is read again (owner, 7 Nov: "it was vanishing all the data for a sec and then bringing it
    // all back"); a new theme or market clears them in run()
    setDiveError(null);
    const again = refreshed.current; refreshed.current = false;
    // LIVE10A-008: a kept dive behind a newer close comes at once marked "updating" while the server reads the new one; the page asks
    // again a few times, quietly, and takes the new one when it is in
    let diveTimer: ReturnType<typeof setTimeout> | undefined, diveTries = 0;
    const getDive = (fresh: boolean) => themeApi.dive(region, q, fresh).then((d) => {
      if (!live) return;
      setDive(d);
      if (d.updating && ++diveTries <= DIVE_TRIES) diveTimer = setTimeout(() => getDive(false), DIVE_EVERY_MS);
    }).catch((e) => { if (live && !diveTries) setDiveError((e as Error).message); });
    getDive(again);
    setNewsBusy(true); themeApi.news(region, q).then((n) => live && setNews(n.items)).catch(() => live && setNews(null)).finally(() => live && setNewsBusy(false));
    themeApi.business(region, q).then((b) => live && setBiz(b)).catch(() => live && setBiz(null));
    // LIVE7A-007: the server matches new listings beside the request and answers "pending" meanwhile; the page asks again a few times
    let ipoTimer: ReturnType<typeof setTimeout> | undefined, ipoTries = 0;
    const listings = () => themeApi.listings(region, q).then((l) => {
      if (!live) return;
      // LIVE9A-022: still matching after the last ask: said as not checked, never "Loading the issues…" left on the page
      if (l.pending && ipoTries + 1 >= LISTING_TRIES) { setIpos({ items: [], checked: false }); return; }
      setIpos(l);
      if (l.pending && ++ipoTries < LISTING_TRIES) ipoTimer = setTimeout(listings, PRICE_EVERY_MS);
    }).catch(() => live && setIpos({ items: [], checked: false }));
    listings();
    return () => { live = false; if (ipoTimer) clearTimeout(ipoTimer); if (diveTimer) clearTimeout(diveTimer); setNewsBusy(false); };
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [key]);
  // prices: read at a gentle pace on the server; asked again while some companies are still waiting
  useEffect(() => {
    if (!dive || !q || dive.members === 0) { setPrices(null); setPricesBusy(false); return; }
    let live = true, tries = 0, timer: ReturnType<typeof setTimeout> | undefined;
    // busy while a read is out or another is coming: the bar stops when the page stops asking, even with some prices still not read
    // (owner, 7 Nov: "after finishing it's still loading")
    // LIVE10A-008: the bar shows for the first read only; the companies still waiting are asked for again quietly and the note under the
    // table says how many are not read yet ("Reading the rest of the companies' price histories…" stayed on Semiconductors and Automotive)
    const go = () => {
      if (!tries) setPricesBusy(true);
      themeApi.prices(region, q).then((p) => {
        if (!live) return;
        setPrices(p);
        setPricesBusy(false);
        if (p.pending > 0 && ++tries < PRICE_TRIES) timer = setTimeout(go, PRICE_EVERY_MS);
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
  const olderTries = useRef(0);
  useEffect(() => { olderTries.current = 0; }, [q, region]);
  useEffect(() => {
    if (!r?.older?.rechecking || olderTries.current >= OLDER_TRIES) return;
    const t = setTimeout(() => { olderTries.current++; run(q, { keep: true }); }, OLDER_EVERY_MS);
    return () => clearTimeout(t);
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [r]);
  const draftIt = async () => {
    setDraft("Drafting…");
    try { const d = await themeApi.draft(region, q); setDraft(d.result === "nothing notable" || d.result === "too few figures" ? "The theme needs two layers with margin figures for a post." : d.slug ? `Draft saved (${d.result}). It is hidden: read it under Admin, Blog, and publish it there if it is right.` : `Not drafted: ${d.problem ?? d.result}.`); }
    catch (e) { setDraft((e as Error).message); }
  };
  // LIVE6-017: the section links sit at the top, under the theme's head, not halfway down the page after the companies
  const nav = r ? [
    { id: "theme-members", label: "Companies" },
    ...(dive && dive.members > 0 ? [{ id: "theme-chain", label: "The chain" }] : []), ...(dive?.layers.some((l) => l.companies.length > 0) ? [{ id: "layer-0", label: "Layers" }] : []), ...(dive?.subs.length ? [{ id: "theme-subs", label: "Sub-themes" }] : []),
    ...(r.tailwinds.length + r.risks.length > 0 ? [{ id: "theme-claims", label: "Tailwinds and risks" }] : []), ...(dive ? [{ id: "theme-news", label: "Latest" }] : []),
    ...(dive && dive.members > 0 ? [{ id: "numbers-size", label: "The theme in numbers" }, { id: "numbers-leaders", label: "Every company" }] : []),
  ] : [];
  return (
    <div className="k-page">
      {/* owner, 18 Nov ("fix ui dude"): one line under the title; how a theme is mapped is behind the (i) */}
      <PageHeader eyebrow={eyebrowOf("/research/themes")} title="Map a theme, find the companies in it"
        lede="Type a sector or trend to see the listed companies along its chain." infoLabel="How a theme is mapped"
        info="Every listed company the exchange classifies in the theme's industries is in it; the AI maps them along the chain and adds companies from other industries, each checked against its own description. The margins, growth and prices beside them are worked out from reported figures." />
      <ThemeBox region={region} setRegion={switchMarket} text={text} setText={setText} current={q} busy={busy} onGo={go} />
      {/* R19: the themes the person saved, each with when it was last read, Open, Update (what changed since), Rename and Remove */}
      <SavedList kind="theme" id="saved-themes" title="Your saved themes" />
      {error && <ErrorState title="The theme couldn't be mapped" action={{ label: "Try again", onClick: () => run(q, { refresh: true }) }}>{error}</ErrorState>}
      {busy && !r && <Card><Skeleton label={`Mapping "${q}"`} lines={4} /></Card>}
      {r && (
        <>
          <Card>
            <CardHead title={r.sector} actions={<><StoredStamp at={r.generated_at > 0 ? r.generated_at : null} tz={marketTz(region)} busy={busy || rf.busy} onRefresh={refresh}
              label={mapStamp(r.generated_at > 0 ? r.generated_at : null, r.older?.at ?? r.checked_at, writtenAt(r.generated_at, marketTz(region)), fmtDate, marketTz(region))} />
              <SaveButton kind="theme" label="Save theme" name={r.sector || q} params={{ q, region }} snap={() => (themeReady(r) ? themeSnap(r) : null)} />
              {themeReady(r) && <ShareResearchButton kind="theme" region={region} target={q} label="this theme" />}</>} />
            <StoredNote busy={rf.busy} state={rf.state} at={r.generated_at > 0 ? r.generated_at : null} tz={marketTz(region)} />
            {olderNote(r.older, fmtDate) && <p className="k-note" data-testid="theme-older">{olderNote(r.older, fmtDate)}</p>}
            {r.summary && <p className="k-lede">{r.summary}</p>}
            {/* LIVE13A-020 (LIVE12A-021): after a colon the phrase keeps its own capital ("converges on Leading-edge…" read as a typo) */}
            {r.core && <p className="k-small">The point everything converges on: <b>{r.core}</b>.</p>}
            <ThemeDownloads r={r} dive={dive} region={region} theme={q} />
            {/* L4: the theme's companies as tiles, grouped by layer, sized by market value and coloured by what the price did */}
            {r.value_chain.some((v) => v.companies.length > 0) && (
              <div className="k-row" data-testid="theme-heatmap">
                <span className="k-small k-muted">See</span>
                <Link className="btn quiet sm" to={`/invest/heatmap?theme=${encodeURIComponent(q)}&region=${region}`}>Heatmap of this theme</Link>
              </div>
            )}
            {themeFunds(r.etfs).funds.length > 0 && (
              <DataTable label="Funds that track the theme" columns={[
                { key: "t", header: "Fund", rowHeader: true, cell: (e: (typeof r.etfs)[number]) => <Link className="link" to={`/research/${region}/${encodeURIComponent(e.ticker)}`}><b>{e.ticker}</b></Link> },
                { key: "n", header: "Name", wrap: true, cell: (e) => fundName(e.name) }]} rows={themeFunds(r.etfs).funds} rowKey={(e) => e.ticker} />
            )}
            {/* LIVE11A-011: a whole-market index fund is not offered as a theme's fund; said once */}
            {themeFunds(r.etfs).broad > 0 && <p className="k-note" data-testid="theme-funds-broad">{themeFunds(r.etfs).broad === 1 ? "A fund that tracks the whole market is left out: it holds far more than this theme." : `${themeFunds(r.etfs).broad} funds that track the whole market are left out: they hold far more than this theme.`}</p>}
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
          {nav.length > 1 && <PageNav items={nav} />}
          <MembersCard r={r} region={region} dive={dive} />
          {diveError && <ErrorState title="The theme's numbers couldn't be loaded" action={{ label: "Try again", onClick: () => run(q, { keep: true }) }}>{diveError}</ErrorState>}
          {!dive && !diveError && <Card><Skeleton label="Working out the theme's figures" lines={5} /></Card>}
          {dive && (
            <>
              {dive.updating && <p className="k-note" data-testid="theme-dive-updating">{DIVE_UPDATING}</p>}
              {/* on every theme with figures (owner, 7 Nov: "did you remove the blog button for me too?": it showed only when the figures were notable) */}
              {me?.is_admin && dive.members > 0 && (
                <div className="k-row" data-testid="theme-blog">
                  <span className="k-small k-muted">{draft ?? (dive.notable.length > 0
                    ? "The figures show something notable. A draft post can be made from them; it stays hidden until you publish it."
                    : "A draft post can be made from this theme's figures; it stays hidden until you publish it.")}</span>
                  <button type="button" className="btn quiet sm" onClick={draftIt} disabled={draft === "Drafting…"}>Draft a blog post</button>
                </div>
              )}
              {dive.members === 0 ? (
                <Card><p className="k-small">No company in this theme has stored figures yet: none is in an official industry of the theme, and none the map named has a description that shows it does the work. Try a more specific theme.</p></Card>
              ) : <ChainCard dive={dive} />}
              {dive.figures && dive.figures.of > dive.figures.shown && <p className="k-note">The figures below are for {dive.figures.shown} of the theme's {dive.figures.of.toLocaleString("en-IN")} companies: every one the map names, then the largest of the rest by market value.</p>}
              {biz && !biz.allowed && dive.region === "IN" && <p className="k-note">Operating figures that companies file between results (monthly sales, output, traffic) are on the Basic plan.</p>}
              {/* LIVE9A-022: a layer with no listed company is named in one line, not a card of its own that says it is empty */}
              {dive.layers.filter((l) => l.companies.length > 0).map((l, i) => <LayerCard key={l.layer} layer={l} i={i} region={dive.region} business={bizFor(biz, l)} />)}
              {emptyLayerLines(dive.layers).map((t) => <p key={t} className="k-note" data-testid="layers-empty">{t}</p>)}
              <SubThemesCard dive={dive} business={biz} />
              <ThemeLinksCard region={dive.region} theme={q} />
            </>
          )}
          <ClaimsCard tailwinds={r.tailwinds} risks={r.risks} />
          {dive && <NewsCard items={news} loading={newsBusy} />}
          {dive && <ChangesCard dive={dive} />}
          {dive && dive.members > 0 && (
            <>
              <h2 className="k-section-title" id="theme-numbers">The theme in numbers</h2>
              <p className="k-note">Reported figures from each company's stored page{dive.as_of ? `, prices to the ${fmtDate(dive.as_of)} close${dive.as_of_older ? ` (${dive.as_of_older.toLocaleString("en-IN")} ${dive.as_of_older === 1 ? "company" : "companies"} at an earlier close)` : ""}` : ""}; the sections below say what each is on.</p>
              <NumbersCards dive={dive} prices={prices} pricesBusy={pricesBusy} />
              <ListingsCard items={ipos && ipos.checked ? ipos.items : null} checked={(ipos?.checked || ipos?.pending) ?? true} region={dive.region} />
            </>
          )}
          <CardNote summary="About this page"><p>The text on this page that describes how a layer or sub-theme works is written by AI from general knowledge, with no figures. Every company of the theme's official industries is listed, whatever the AI says; a company the AI added from another industry is kept only while its own description doesn't show otherwise, with its words shown where they confirm the work. Every figure is from the companies' reported numbers or stored pages, with its year and basis.</p></CardNote>
        </>
      )}
    </div>
  );
}

/** The theme box (owner, 18 Nov: "fix ui dude"): the market switch, the box and "Map it" on one row; under it the market's ready themes as
 *  compact chips, A to Z, each with the day its map was updated inside it (site87, owner: 31 equal heavy pills, a "Fewer themes" button and a
 *  tooltip over the next row); then the ideas this market's chips don't already show (never the same theme twice, never the other market's). */
function ThemeBox({ region, setRegion, text, setText, current, busy, onGo }: { region: "IN" | "US"; setRegion: (r: "IN" | "US") => void; text: string;
  setText: (t: string) => void; current: string; busy: boolean; onGo: (t: string) => void }) {
  const items = useLibrary(region, text).filter((i) => !foreignTheme(i.name, region));
  const matching = items.filter((i) => i.name.toLowerCase() !== current.trim().toLowerCase());
  const ideas = ideasBeside(THEME_IDEAS[region], items, region, shortTheme);
  return (
    <Card className="theme-box">
      <form className="theme-map" aria-label="Map a theme" onSubmit={(e) => { e.preventDefault(); onGo(text); }}>
        <RegionSwitch region={region} setRegion={setRegion} />
        <div className="theme-field">
          <label htmlFor="theme-q" className="sr-only">Theme</label>
          <input id="theme-q" className="k-input" value={text} onChange={(e) => setText(e.target.value)}
            placeholder={region === "IN" ? "India defence, railways capex…" : "AI data centers, grid electrification…"} />
          <button className="btn" disabled={busy}>{busy ? "Mapping…" : "Map it"}</button>
        </div>
      </form>
      <ReadyGrid items={matching} onPick={onGo} />
      {ideas.length > 0 && (
        <div className="k-row theme-ideas" data-testid="theme-ideas"><span className="k-small k-muted">{matching.length ? "Other ideas" : "Or try"}</span>
          {ideas.map((t) => <button key={t} type="button" className="theme-chip idea" onClick={() => onGo(t)}>{t}</button>)}</div>
      )}
    </Card>
  );
}

/** The shared library: themes StratLab has mapped and kept once for everyone that match what's typed, so a search for one of them opens
 *  at once (R19). Not this account's reading history, so it is headed "Ready to open" with the date the map was updated (LIVE6-012).
 *  Signed-in only, as the page is; nothing shows until there is one. */
function useLibrary(region: "IN" | "US", typed: string): LibraryTheme[] {
  const [items, setItems] = useState<LibraryTheme[]>([]);
  useEffect(() => {
    let live = true;
    setItems([]);                       // site87: never a moment of the other market's chips after a switch
    const t = setTimeout(() => {
      themeApi.suggest(region, typed.trim()).then((x) => live && setItems(x.items.filter((i) => !i.region || i.region === region))).catch(() => live && setItems([]));
    }, 250);
    return () => { live = false; clearTimeout(t); };
  }, [region, typed]);
  return items;
}

/** Lines of chips the ready area shows before it scrolls inside itself (it scrolls only when that hides three lines or more). */
const READY_LINES = 3;

/** Ready to open: every ready theme of the market as a compact chip, A to Z: its short name and, small inside it, the day its map was
 *  updated (its full name in the chip's accessible name, no hover box over the next chips). Past READY_LINES lines the area scrolls inside
 *  itself, so no "All N themes" / "Fewer themes" button (site87, owner: no show-more control on any list). */
function ReadyGrid({ items, onPick }: { items: LibraryTheme[]; onPick: (t: string) => void }) {
  const grid = useRef<HTMLDivElement>(null);
  const [over, setOver] = useState(false);
  const sorted = [...items].sort((a, b) => shortTheme(a.name).localeCompare(shortTheme(b.name)));
  useLayoutEffect(() => {
    const el = grid.current;
    if (!el) return;
    const look = () => {
      el.style.maxHeight = "";
      const kids = Array.from(el.children) as HTMLElement[];
      const tops = Array.from(new Set(kids.map((k) => Math.round(k.offsetTop)))).sort((a, b) => a - b);
      const cut = tops.length - READY_LINES >= 3 ? tops[READY_LINES] : null;
      el.toggleAttribute("data-over", cut != null);
      if (cut != null) el.style.maxHeight = `${cut - 4}px`;
      el.toggleAttribute("data-more", cut != null && el.scrollHeight - el.clientHeight - el.scrollTop > 2);
      setOver(cut != null);
    };
    look();
    const more = () => el.toggleAttribute("data-more", el.hasAttribute("data-over") && el.scrollHeight - el.clientHeight - el.scrollTop > 2);
    el.addEventListener("scroll", more, { passive: true });
    const stop = watchSize(el.parentElement ?? el, look);
    return () => { stop(); el.removeEventListener("scroll", more); };
  }, [sorted.length]);
  if (!items.length) return null;
  return (
    <div className="theme-already" data-testid="theme-already">
      <span className="k-small k-muted" id="theme-ready-head">{LIBRARY_HEAD}</span>
      <div className="theme-ready" ref={grid} role={over ? "region" : undefined} aria-labelledby={over ? "theme-ready-head" : undefined} tabIndex={over ? 0 : undefined}>
        {sorted.map((i) => {
          const day = i.day ?? (i.at ? i.at.slice(0, 10) : null);
          return (
            <button key={i.q} type="button" className="theme-chip" aria-label={libraryLabel(i, (d) => fmtDate(d, { year: false }), false)} onClick={() => onPick(i.name)}>
              <span className="theme-chip-name">{shortTheme(i.name)}</span>
              {day && <small className="theme-chip-day" aria-hidden="true">{fmtDate(day, { year: false })}</small>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
