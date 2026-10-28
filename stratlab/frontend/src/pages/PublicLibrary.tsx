import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { publicGet, type ApiError } from "../lib/http";
import { applySeo, seoFor } from "../lib/seo";
import { absolute } from "../content/seo";
import { groupLabel, plainTerms } from "../lib/plainTerms";
import { pct, TF_NAME } from "../lib/format";
import { signedInHere, signIn } from "../lib/signin";
import { Search } from "../components/Icons";
import { OpenApp, PublicFrame } from "../components/PublicFrame";
import { adsLive } from "../lib/ads";
import { CONFIG } from "../lib/adsConfig";
import { CHECK_RESULT, CHECKS_NOT_HOLD, checksOf, headTone, HoldLine, LibraryCard, libraryTally, liveOptions, marketChoices, Rules, shownStats, strategyName, libMeta, testedRange, trails, unseenLabel, VERDICTS, whereShown, type LibEntry } from "../components/LibraryBits";
import { libraryDescription, libraryTitle } from "../lib/libraryText";
import { Badge } from "../components/kit/Badge";
import { Card, CardHead } from "../components/kit/Card";
import { ChipBar } from "../components/kit/ChipBar";
import { Select } from "../components/kit/Form";
import { PageHeader } from "../components/kit/PageHeader";
import { Stat, StatRow } from "../components/kit/Stat";
import { EmptyState, ErrorState, Skeleton } from "../components/kit/States";
import "./trade/trade.css";

// ADS-1: the ad slot's code loads only when ads can draw here; with ads off (the default) the page asks for no extra file
// (R8V-013 counts the library's files). A public slot with ads off shows nothing either way (lib/ads.ts adMode).
const ADS_HERE = adsLive(CONFIG, "public");
const PublicAdLazy = lazy(() => import("../components/AdUnit").then((m) => ({ default: m.PublicAd })));
const PublicAd = () => (ADS_HERE ? <Suspense fallback={null}><PublicAdLazy /></Suspense> : null);

/* StratLab's own library strategies, open to anyone and read only: the rules that were tested and the verdict each earned,
 * as the app's own backtest gave it. Copying one and re-testing it needs an account, so that button says it goes to Google.
 * Only entries StratLab published itself come from the server (/public/library), never a user's. */

const CHECK_NAME: Record<string, string> = { unseen: "Unseen part", nearby: "Nearby settings", shuffle: "Bad-luck drawdown", sample: "Enough trades" };
/** What each check asks, so "Not run" and "Passed" mean something to a visitor. */
const CHECK_SAYS: Record<string, string> = {
  unseen: "Did it make money on the last part of the period, which the rules weren't tuned on?",
  nearby: "Do settings near the chosen ones make money too? Not run on a group of stocks.",
  shuffle: "With the same trades in a worse order, how much deeper could the worst fall have been?",
  sample: "Were there enough trades to tell skill from luck (30 or more)?",
};
const NOTE = "Tested by StratLab on past prices, for research and paper trading. Each entry's dates are the prices its latest test covered. A verdict describes the past, not what comes next, and nothing here is investment advice.";

/** How a group was tested, so the totals can be read (R43B-004): one pot of capital, buy and hold in equal parts, and
 *  the group as it is today. */
export const GROUP_BASIS = "Every stock in the group was tested as one pot of capital. Buy and hold puts an equal share into each stock at the start. "
  + "The group is its members today, so companies that left it during the period aren't in the test; that flatters both figures.";

const where = (e: LibEntry) => e.group ? groupLabel(e.group.name, e.group.members?.length) : e.instrument?.symbol ?? e.market;
const tone = (n: number | null) => (n == null || n === 0 ? undefined : n > 0 ? "up" as const : "down" as const);

/** Signed in already (a saved sign-in in this browser): "Open StratLab" instead of a sign-in that is not needed. */
const GoogleCopy = ({ label = "Continue with Google to copy and re-test", small = false }: { label?: string; small?: boolean }) => (
  signedInHere() ? <OpenApp className={small ? "btn sm" : "btn"} /> : <button type="button" className={small ? "btn sm" : "btn"} onClick={() => void signIn("/library")}>{label}</button>
);

/** /library, signed out: StratLab's own strategies with their verdicts. */
export function PublicLibrary() {
  const [rows, setRows] = useState<LibEntry[] | null>(null);
  const [counts, setCounts] = useState<Record<string, number> | undefined>(undefined);
  const [failed, setFailed] = useState(false);
  const [again, setAgain] = useState(0);
  const [q, setQ] = useState("");
  const [verdict, setVerdict] = useState("");
  const [market, setMarket] = useState("");
  useEffect(() => {
    let live = true;
    setFailed(false);
    publicGet<{ entries: LibEntry[]; markets?: Record<string, number> }>("/public/library").then((r) => { if (live) { setRows(r.entries); setCounts(r.markets); } }).catch(() => { if (live) { setRows([]); setFailed(true); } });
    return () => { live = false; };
  }, [again]);
  const shown = useMemo(() => (rows ?? []).filter((e) => (!verdict || e.verdict.verdict === verdict) && (!market || e.market === market)
    && (!q.trim() || `${e.name} ${e.description} ${where(e)}`.toLowerCase().includes(q.trim().toLowerCase()))), [rows, q, verdict, market]);
  // only the choices some strategy matches; the one picked stays so it can be undone (DK-015)
  const verdicts = useMemo(() => liveOptions(VERDICTS, rows ?? [], (e) => e.verdict.verdict, verdict), [rows, verdict]);
  // the markets that have a strategy, each with how many (MO-5b)
  const markets = useMemo(() => marketChoices(counts, rows ?? [], market), [counts, rows, market]);
  const tally = useMemo(() => libraryTally(rows ?? []), [rows]);
  return (
    <PublicFrame action={<GoogleCopy label="Continue with Google" small />}>
      <PageHeader eyebrow="Strategy library" title="StratLab's own strategies"
        lede="Well-known rule sets that StratLab ran through its own backtest and four checks, each shown with the verdict it earned, the ones that failed as plainly as the ones that held up. Open one to read its rules." />
      <Card label="Find a strategy">
        <div className="k-toolbar">
          <label className="k-search"><Search size={18} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search: RSI, breakout, NIFTY" aria-label="Search the library" /></label>
          <Select label="Verdict" value={verdict} onChange={setVerdict} options={verdicts.map(([value, label]) => ({ value, label }))} />
        </div>
        {markets.length > 2 && <ChipBar label="Market" options={markets} value={market} onChange={setMarket} wrap />}
      </Card>
      {rows === null ? <Card><Skeleton label="Opening the library" /></Card>
        : failed ? <ErrorState title="The library couldn't be opened" action={{ label: "Try again", onClick: () => setAgain((x) => x + 1) }}>Your connection or ours dropped for a moment.</ErrorState>
        : shown.length === 0 ? <EmptyState title={rows.length ? "Nothing matches that." : "There are no strategies to show yet."}>{rows.length ? "Clear the search or the filters to see them all." : "Check back soon."}</EmptyState>
        : (
          <>
            {/* what the list adds up to, from its data, and what the checks mean once (DK-014: every card repeated it) */}
            <div className="k-stack k-tight">
              <p className="k-small" data-testid="lib-summary"><b>{tally.line}</b></p>
              <p className="k-note" data-testid="lib-checks-not-hold">{CHECKS_NOT_HOLD} Points are the gap in total return after costs, over the same dates.</p>
              {/* only when a search or a filter narrows the list: the summary above already counts them all (VR1-171) */}
              {shown.length !== rows.length && <span className="k-small k-muted">{shown.length} of {rows.length} strategies shown</span>}
            </div>
            <div className="k-cards lib-cards">
              {shown.map((e) => (
                <Card key={e.id} label={`${strategyName(e)}, ${libMeta(e)}`} className="lib-card lib-lean">
                  {/* the same face as the signed-in library's; the rules and the checks one by one are on the strategy's own page */}
                  <LibraryCard e={e} details={false} actions={
                    <Link className="btn sm" to={`/library/${encodeURIComponent(e.id)}`} aria-label={`Open the verdict and rules of ${strategyName(e)}, ${libMeta(e)}`}>Open the verdict and rules</Link>} />
                </Card>
              ))}
            </div>
          </>
        )}
      <p className="k-note">{NOTE}</p>
      {/* ADS-1: one slot, below the list (a page with nothing on it yet has no ad), clear of the cards' buttons; nothing while ads are off */}
      {shown.length > 0 && <PublicAd />}
    </PublicFrame>
  );
}

/** /library/<id>, signed out: one StratLab strategy with its verdict, its four checks, its figures and its rules. */
export function PublicLibraryEntry({ id }: { id: string }) {
  const [e, setE] = useState<LibEntry | null>(null);
  const [gone, setGone] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [again, setAgain] = useState(0);
  useEffect(() => {
    let live = true;
    setE(null); setGone(null); setFailed(false);
    publicGet<LibEntry>(`/public/library/${encodeURIComponent(id)}`)
      .then((r) => { if (live) setE(r); })
      .catch((x: ApiError) => { if (!live) return;
        // only a 404 is "not in the library"; a failed fetch is a connection problem, said so with a Retry
        if (x.status === 404) { setGone("That strategy isn't in StratLab's library."); document.title = "Strategy not found · StratLab"; } else setFailed(true); });
    return () => { live = false; };
  }, [id, again]);
  useEffect(() => {
    if (!e) return;
    // the result first, as the page's headline leads with it, and the universe once (R7V-006)
    const title = libraryTitle(plainTerms(e.name), e.verdict.fact_headline, e.verdict.label ?? e.verdict.headline);
    document.title = title;
    const desc = libraryDescription({ name: plainTerms(e.name), where: where(e), group: e.group?.name, factHeadline: e.verdict.fact_headline,
      headline: e.verdict.headline, reason: e.reason });
    applySeo({ ...seoFor(`/library/${id}`, "public"), description: desc, canonical: absolute(`/library/${id}`), index: true }, title);
  }, [e, id]);
  const sh = e ? shownStats(e) : null;
  return (
    <PublicFrame action={<GoogleCopy label="Continue with Google" small />}>
      {!e && !gone && !failed && <><h1 className="sr-only">Opening the strategy</h1><Card><Skeleton label="Opening the strategy" /></Card></>}
      {/* the page's one heading, also when the strategy is gone (R7O-010, axe page-has-heading-one) */}
      {failed && <><h1 className="k-h1">StratLab couldn't load this page</h1><ErrorState title="The strategy couldn't be opened" action={{ label: "Retry", onClick: () => setAgain((x) => x + 1) }}>Check your connection and try again.</ErrorState></>}
      {gone && <><h1 className="k-h1">This strategy isn't available</h1><ErrorState title="Not in the library" action={{ label: "See StratLab's strategies", to: "/library" }}>{gone}</ErrorState></>}
      {e && sh && (
        <>
          <div className="k-stack">
            <span className="k-eyebrow">{[plainTerms(e.name), whereShown(plainTerms(e.name), where(e), e.group?.name), `${TF_NAME[e.tf] ?? e.tf} candles`].filter(Boolean).join(" · ")}</span>
            {/* the result in the checks' own words, with buy and hold beside it, the same words as the library card (R6V-005) */}
            <h1 className={`verdict-head pub-head ${headTone(e)}`} data-testid="lib-headline">{e.verdict.fact_headline ?? e.verdict.headline}</h1>
            <p className="k-lede">{e.verdict.fact_summary ?? e.verdict.summary}</p>
            <HoldLine e={e} />
            <span className="k-note k-row"><Badge tone="ok" dot={false}>{e.badge ?? "StratLab"}</Badge><span data-testid="lib-tested">{e.range ? `Tested ${testedRange(e.range)}` : "Tested on past prices"}</span></span>
          </div>
          <Card label="Results">
            <CardHead title="Results after costs, total over the test" actions={<span className="k-note">{checksOf(e)}</span>} />
            <StatRow label="Results">
              <Stat item label="Total return after costs" value={sh.ret == null ? "–" : pct(sh.ret)} tone={trails(e) ? undefined : tone(sh.ret)} />
              <Stat item label="Total buy and hold" value={sh.buy_hold == null ? "–" : pct(sh.buy_hold)} tone={tone(sh.buy_hold)} />
              <Stat item label={unseenLabel(e)} value={sh.unseen == null ? "–" : pct(sh.unseen)} tone={tone(sh.unseen)} />
              <Stat item label="Worst fall" value={sh.mdd == null ? "–" : pct(sh.mdd)} tone={sh.mdd == null ? undefined : "down"} />
              <Stat item label="Trades" value={e.stats.trades == null ? "–" : String(e.stats.trades)} />
            </StatRow>
            {e.group && <p className="k-small k-muted" data-testid="lib-group-basis">{GROUP_BASIS}</p>}
          </Card>
          {!!e.verdict.checks?.length && (
            <section className="pub-checks" aria-label="The four checks">
              {e.verdict.checks.map((c) => (
                <Card key={c.id} label={c.id === "unseen" ? unseenLabel(e) : CHECK_NAME[c.id] ?? c.id}>
                  <CardHead level={3} title={c.id === "unseen" ? unseenLabel(e) : CHECK_NAME[c.id] ?? c.id} actions={<Badge tone={c.status === "pass" ? "ok" : c.status === "fail" || c.status === "not_passed" ? "warn" : "plain"}>{CHECK_RESULT[c.status] ?? c.status}</Badge>} />
                  <p className="k-small k-muted">{CHECK_SAYS[c.id]}</p>
                </Card>
              ))}
            </section>
          )}
          <Card label="The rules">
            <CardHead title="The rules that were tested" />
            <Rules s={e.strategy} />
            {e.description && <p className="k-small k-muted">{plainTerms(e.description)}</p>}
          </Card>
          <Card label="Copy and re-test">
            <CardHead title="Test it yourself" />
            {/* signed in, the signed-out "needs a free account" line was wrong and there was nothing to copy with (R57-007) */}
            {signedInHere()
              ? <><p className="k-small k-muted">Copy these rules into your own notebook from the library in StratLab ("Copy and re-test", beside the strategy), then run them on your market and dates.</p>
                <div className="k-row"><a className="btn" href="/library">Open the library in StratLab</a></div></>
              : <><p className="k-small k-muted">Copy these rules into your own notebook and run them on your market and dates. Copying needs a free account; signing in only reads your name and email from Google.</p>
                <div className="k-row"><GoogleCopy /><Link className="btn quiet" to="/library">All StratLab strategies</Link></div></>}
          </Card>
          <p className="k-note">{NOTE}</p>
          <PublicAd />
        </>
      )}
    </PublicFrame>
  );
}
