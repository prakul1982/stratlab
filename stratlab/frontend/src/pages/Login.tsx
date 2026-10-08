import { useEffect, useId, useRef, useState, type JSX, type KeyboardEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { money, usePricing } from "../lib/currency";
import { canBuy, finePrint, landingAction, pricingIntro, YEARLY_LABEL, yearlySaving } from "../lib/offer";
import { FEATURES, LIMITS, PLAN_IDS, PLAN_NAME, PRICE, WHO, type PlanId } from "../lib/plans";
import { signIn } from "../lib/signin";
import { signInProblem } from "../lib/signinError";
import { FAQ } from "../content/faq";
import { Google } from "../components/Icons";
import { LegalLinks } from "../components/LegalLinks";
import { Logo } from "../components/Logo";
import { SkipLink } from "../components/SkipLink";
import { Seg } from "../components/kit/Seg";
import { Dialog } from "../components/kit/Dialog";
import { publicGet } from "../lib/http";
import { plainTerms } from "../lib/plainTerms";
import { checksLine } from "../lib/tradeUi";
import type { LibEntry } from "../components/LibraryBits";

/* The public landing page: what StratLab does, in its three spaces (Trade, the strategy lab it began as, first; then
 * Invest and Money), the alerts across them, the plans, and one way in (Google sign-in). Every button that signs in
 * says so ("Continue with Google"); a button that needs an account for what it opens says that too. */

type Status = "pass" | "warn" | "fail";
const STATUS: Record<Status, string> = { pass: "Passed", warn: "Warning", fail: "Failed" };

/** Three sample ideas for the hero demo: what you write, how it's read, what the verdict says. */
const DEMOS: {
  tab: string; idea: string; rule: [string, boolean][]; meta: string; verdict: string; tone: "blue" | "orange" | "ink"; why: string; checks: [string, Status][];
}[] = [
  {
    tab: "NIFTY 50", idea: "Buy NIFTY 50 when the 20-day average crosses above the 50-day, with a 2% stop loss",
    rule: [["Buy when", false], ["SMA 20", true], ["crosses above", true], ["SMA 50", true], ["· stop loss", false], ["2%", true]],
    meta: "Experiment v3 · NIFTY 50 · 38 trades", verdict: "Failed on unseen years.", tone: "orange",
    why: "It made money on the years it was tuned on, then lost on years it had never seen.",
    checks: [["Unseen data", "fail"], ["Nearby settings", "fail"], ["Bad-luck drawdown", "warn"], ["Enough trades", "pass"]],
  },
  {
    tab: "Bitcoin", idea: "Buy Bitcoin when RSI drops below 30, sell when it goes back above 55",
    rule: [["Buy when", false], ["RSI 14", true], ["falls below", true], ["30", true], ["· sell when above", false], ["55", true]],
    meta: "Experiment v5 · BTC/USD · 61 trades", verdict: "Held up on unseen years.", tone: "blue",
    why: "It kept working on data it had never seen, and small changes to the settings didn't break it.",
    checks: [["Unseen data", "pass"], ["Nearby settings", "pass"], ["Bad-luck drawdown", "warn"], ["Enough trades", "pass"]],
  },
  {
    tab: "NVIDIA", idea: "Short NVDA when it falls below its 20-day low, with a 5% trailing stop",
    rule: [["Sell short when", false], ["price", true], ["falls below", true], ["20-day low", true], ["· trail the stop", false], ["5%", true]],
    meta: "Experiment v1 · NVDA · 9 trades", verdict: "Too few trades to tell.", tone: "ink",
    why: "Nine trades in five years is too few to tell skill from chance. Try a longer period or a looser rule.",
    checks: [["Unseen data", "warn"], ["Nearby settings", "pass"], ["Bad-luck drawdown", "pass"], ["Enough trades", "fail"]],
  },
];

const CHECKS: { title: string; body: string; art: JSX.Element }[] = [
  { title: "Unseen data", body: "Does it still make money on the 30% of years it was never tuned on?", art: <ArtUnseen /> },
  { title: "Nearby settings", body: "Do small changes to its settings still work, or only your exact numbers?", art: <ArtNearby /> },
  { title: "Bad-luck drawdown", body: "How deep could the losses get with worse luck, over 1,000 reshuffles?", art: <ArtDrawdown /> },
  { title: "Enough trades", body: "Under 15 trades, luck dominates; 30 or more is a fair sample.", art: <ArtTrades /> },
];

/* What StratLab does today, in the spaces the page is built around, one short line each. Facts about the product only:
 * nothing here says what to buy or sell, rates a company or names a data source. */
const RESEARCH: [string, string][] = [
  ["Company pages", "Any NSE, BSE or US company: price, key numbers, results, owners and news."],
  ["Deep dive", "Ten years of numbers, then the business and its plans in its own words."],
  ["Report card and checklist", "What management promised on past calls, against what followed."],
  ["Results calendar", "Results meetings and report dates, a week back to four weeks ahead."],
  ["Corporate actions", "Dividends, bonuses, splits and buybacks by ex-date and record date."],
  ["Deals and insider trades", "Promoters' and directors' own trades, pledges, bulk and block deals."],
  ["Surveillance lists", "ASM, GSM, ESM, trade-to-trade and the F&O ban, and what each means."],
  ["Filings and red flags", "Fund raises, pledges, resignations and defaults, linked to the filing."],
  ["Screens", "Filter by size, growth, debt, returns and more; new matches by email."],
  ["Stage 2 scan", "Stocks in Stage 2 with the Supertrend up, fresh signals first."],
  ["Sector rotation", "Every sector against the market: leading, weakening, lagging, improving."],
  ["Market breadth", "How many stocks rose, fell, or sit above their 20, 50 and 200-day averages."],
  ["Price charts", "Candles, Heikin-Ashi or bars, indicators, drawings kept on your account, and compare."],
  ["ETF price vs NAV", "How far each ETF trades from what a unit holds, with 30 days of history."],
  ["Watchlist at a glance", "Trend, sector rotation, red flags and checklist for each company you follow."],
  ["Compare", "Two companies side by side on the same numbers."],
];

const PORTFOLIO: [string, string, string][] = [
  ["My Holdings", "From your broker's file: Zerodha, Groww, Upstox, Angel One and more.", "Seen only by you"],
  ["Tax report", "Capital gains from your tradebooks or their ZIP, first in, first out.", "An estimate for your CA"],
  ["Mutual funds", "Your CAMS or KFintech statement: value, XIRR and gains by year.", "Never fund ratings"],
  ["Fund costs", "Each fund's expense ratio in rupees a year, direct and regular side by side.", "Rupees, not just %"],
  ["Net worth", "Stocks, funds, PF, PPF, NPS, deposits, gold and property, minus loans.", "Each value explained"],
  ["Loans and insurance", "EMIs, interest this year, what a prepayment changes, and premiums due.", "Your own figures"],
  ["Dividends, bonuses and splits", "What's ahead on what you hold; a bonus or split applied in one click.", "Nothing changes without you"],
  ["Tax tools", "Dividends with TDS, advance tax by due date, the exemption left.", "Dates and totals"],
  ["US stocks in Indian tax", "US sales in rupees, the 24-month rule, tax credit and Schedule FA.", "For a resident individual"],
  ["ITR-ready export", "Your year laid out like the ITR schedules, as a spreadsheet or PDF.", "Not a filed return"],
  ["Money calendar", "Tax dates, results, dividends, maturities and EMIs in one feed.", "Dates only"],
  ["Share cards and invites", "Share a company's facts as a card; invite friends for a month of Basic.", "A month of Basic each"],
];

/** The strategy lab beyond the four steps, one line each. */
const TOOLS: [string, string][] = [
  ["Real trading costs", "STT, stamp duty, GST, exchange fees and slippage, per market."],
  ["Long, short and intraday", "Stops in %, points or ATR, trailing stops, square-off, a daily loss cap."],
  ["Walk-forward test", "Re-tune on the past, trade the stretch the tuning never saw, repeat."],
  ["Whole groups", "One set of rules on NIFTY 50, the F&O stocks, US mega caps or your list."],
  ["Options, live", "Any structure up to eight legs at the real bid and ask."],
  ["Greeks and what-if", "Delta, gamma, theta and vega, the payoff today and at expiry, and sliders."],
  ["After charges", "Breakevens, most it can make and most it can lose, after every charge."],
  ["F&O changes", "Stocks entering or leaving F&O, lot sizes and expiry days, by date."],
  ["Trades on the chart", "Each backtest trade's entry and exit on the candles, with the rules' indicators."],
  ["Paper trading", "Run it live on real prices with fake money, with a report after each close."],
  ["Positioning", "Who holds index futures and options, FII and DII flows, PCR and max pain."],
  ["Trade journal", "Your real trades as round trips after charges, with the same four checks."],
  ["Bring any strategy", "Pine Script, Python, MetaTrader, AmiBroker or plain words."],
  ["Strategy library", "Published rules, each with the result of its checks. Copy and re-test."],
  ["Compare experiments", "Every run saved; two side by side show what changed."],
  ["Share the verdict", "A card or a public link with all four checks. Your rules stay private."],
];

const ALERTS: [string, string][] = [
  ["Stock alerts", "A price, a big move, a moving average, RSI, a Stage change, insider trades or a red flag."],
  ["Results and corporate actions", "Results day, and dividends, bonuses or splits on stocks you follow."],
  ["Market breadth", "When a group's share of stocks above the 50-day average crosses your level."],
  ["Advance tax", "A week and a day before each due date. The amounts stay on the page."],
  ["Money calendar", "One morning message for the dates you pick: tax, results, EMIs, your own."],
  ["Newsletters", "The Market Brief and My Stocks, daily or weekly, by email."],
  ["F&O changes", "When an exit, lot size or expiry change touches your watchlist or paper sessions."],
  ["ETF price vs NAV", "When an ETF you pick trades further above or below its NAV than your level."],
  ["Paper trades", "Each trade as it happens, and a short report after the close."],
];

/** The bitcoin sign, drawn: the page's fonts have no ₿, and the fallback font drew one that read as the baht's ฿. */
function BitcoinSign() {
  return (
    <svg viewBox="0 0 20 20" width="15" height="15" aria-hidden="true" className="lp-btc">
      <text x="10" y="15" textAnchor="middle" fontSize="15" fontWeight="600" fontFamily="var(--sans)" fill="currentColor">B</text>
      <path d="M8.3 1.5v3M11.3 1.5v3M8.3 15.5v3M11.3 15.5v3" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

const MARKETS: [ReactNode, string][] = [
  ["₹", "India"], [<BitcoinSign key="btc" />, "Crypto"], ["$", "United States"], ["£", "United Kingdom"], ["€", "Europe"], ["¥", "Japan"],
  ["€$", "Forex"], ["₹$", "Indian currency futures"], ["₹Au", "Indian commodities"], ["$Au", "Global commodities"], ["+", "Your own data (CSV)"],
];

const SECTIONS: [string, string][] = [["trade", "Trade"], ["invest", "Invest"], ["money", "Money"],
  ["alerts", "Alerts"], ["pricing", "Plans"], ["faq", "FAQ"]];

/** The three spaces, one line and one small picture of the product each, in the order the page tells them. */
const SPACES: [string, string, string, string][] = [
  ["trade", "Trade", "The strategy lab", "Test a trading idea on years of real prices, then paper trade it."],
  ["invest", "Invest", "Research", "Any Indian or US company from its own numbers and filings."],
  ["money", "Money", "What you own", "Holdings, funds, net worth and the year's tax, from your files."],
];

/** A section's eyebrow, heading and one line under it. */
function Head({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <div className="lp-head">
      <span className="eyebrow">{eyebrow}</span>
      <h2 className="serif lp-h2">{title}</h2>
      {children && <p className="lp-p">{children}</p>}
    </div>
  );
}

/** A few tools in view, the rest one click away: the page stays short and nothing is left out. */
function ToolList({ items, label, shown = 4, three = false }: { items: [string, string][]; label: string; shown?: number; three?: boolean }) {
  const tool = ([t, b]: [string, string]) => <div key={t} className="lp-tool"><b>{t}</b><p className="small muted">{b}</p></div>;
  const cls = `lp-tools${three ? " lp-tools-3" : ""}`;
  return (
    <div className="stack">
      <div className={cls}>{items.slice(0, shown).map(tool)}</div>
      {items.length > shown && (
        <details className="lp-more">
          <summary>{items.length - shown} more {label}</summary>
          <div className={cls}>{items.slice(shown).map(tool)}</div>
        </details>
      )}
    </div>
  );
}

const moneyCard = ([t, b, tag]: [string, string, string]) => (
  <div key={t} className="lp-card lp-beyond-card"><b>{t}</b><p className="small muted">{b}</p><span className="lp-tag">{tag}</span></div>
);

/** Close a `<details>` menu with Esc or a tap outside it, the way every other pop-up on the site closes. */
function useDetailsDismiss(ref: React.RefObject<HTMLDetailsElement | null>) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const close = (back: boolean) => { if (el.open) { el.open = false; if (back) el.querySelector("summary")?.focus(); } };
    const key = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") close(true); };
    const down = (e: Event) => { if (!el.contains(e.target as Node)) close(false); };
    document.addEventListener("keydown", key);
    document.addEventListener("pointerdown", down);
    return () => { document.removeEventListener("keydown", key); document.removeEventListener("pointerdown", down); };
  }, [ref]);
}

/** `section`: scroll there first (the page was opened as /pricing, /faq…). `panel`: the address was /login or /signup, so
 * the way in is open on top of the page. */
export function Login({ section = null, panel }: { section?: string | null; panel?: "login" | "signup" } = {}) {
  // Google sends a refused or failed sign-in back with ?error= or #error= in the address: say so at the top, in words
  const [error, setError] = useState<string | null>(() => signInProblem(location.search, location.hash));
  const [way, setWay] = useState(panel ?? null);
  useEffect(() => setWay(panel ?? null), [panel]);
  useEffect(() => {
    if (!section) return;
    const go = () => document.getElementById(section)?.scrollIntoView();
    go();
    const t = window.setTimeout(go, 150);       // once the fonts and the first images have settled the layout
    return () => window.clearTimeout(t);
  }, [section]);
  useEffect(() => {
    if (error && /[?#&]error/.test(location.search + location.hash)) history.replaceState(null, "", location.pathname);
  }, [error]);
  const menu = useRef<HTMLDetailsElement>(null);
  useDetailsDismiss(menu);

  const go = () => { void signIn().catch(() => setError("Couldn't start Google sign-in. Check your connection and try again.")); };
  const cta = (label = "Continue with Google") => (
    <button type="button" className="btn lp-cta" onClick={go}><Google />{label}</button>
  );

  return (
    <div className="lp">
      <SkipLink />
      <header className="lp-nav">
        <a href="#top" className="brand" aria-label="StratLab home"><Logo size={46} /></a>
        <nav aria-label="Sections">
          {SECTIONS.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}
        </nav>
        {/* on a phone the section links fold into a small menu (the row above hides there) */}
        <details className="lp-menu" ref={menu}>
          <summary>Menu</summary>
          <nav aria-label="Sections (menu)" onClick={(e) => { if ((e.target as HTMLElement).closest("a")) (e.currentTarget.parentElement as HTMLDetailsElement).open = false; }}>
            {SECTIONS.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}
          </nav>
        </details>
        <button type="button" className="btn outline sm" onClick={go}>Sign in</button>
      </header>

      {way && (
        <Dialog title={way === "signup" ? "Create your free account" : "Sign in to StratLab"} onClose={() => setWay(null)}>
          <div className="k-stack">
            <p className="k-small">{way === "signup" ? "StratLab accounts are made with Google: there's no password to set up and no card to add." : "StratLab signs in with your Google account."} Signing in only reads your name and email from Google.</p>
            <div className="k-row">{cta()}</div>
          </div>
        </Dialog>
      )}

      <main id="main" tabIndex={-1}>
      <section id="top" className="lp-hero ruled">
        <div className="lp-wrap lp-hero-grid">
          <div className="stack g22 lp-hero-copy">
            <span className="eyebrow">Trade · Invest · Money · Indian and US stocks</span>
            <h1 className="serif lp-h1"><em>Test</em> it, research it, track it.</h1>
            <p className="serif lp-lede">One place for trading ideas, company research and your own money. Facts and tests, never tips.</p>
            <div className="row wrap g12">
              {cta()}
              <a className="btn quiet lp-cta-2" href="#trade">See how it works</a>
            </div>
            {error && <p className="banner" role="alert">{error}</p>}
            <p className="small muted">Free to start · No card · No code · Paper trading only, no real orders</p>
          </div>
          <HeroDemo />
        </div>
      </section>

      <section className="lp-sec lp-spaces-sec" aria-labelledby="spaces-h">
        <div id="about" className="lp-wrap stack g24">
          <h2 id="spaces-h" className="serif lp-h3">Three spaces, one place.</h2>
          <div className="lp-spaces">
            {SPACES.map(([id, name, sub, what]) => (
              <a key={id} href={`#${id}`} className="lp-card lp-space" data-space={id}>
                <span className="eyebrow">{sub}</span><b className="serif">{name}</b><p className="small muted">{what}</p>
                <SpaceArt space={id} />
                <span className="small lp-space-go">See {name} ↓</span>
              </a>
            ))}
          </div>
        </div>
      </section>

      <section id="trade" className="lp-sec lp-alt">
        <div className="lp-wrap stack g36">
          <Head eyebrow="Trade · the strategy lab" title="From a sentence to a verdict.">
            Most backtests are tuned until the curve looks good. StratLab tests the idea on real prices after real costs, then checks whether the result holds up.
          </Head>
          <ol className="lp-steps">
            <li className="lp-card"><span className="lp-num">1</span><b>Describe it</b><p className="small muted">"Buy Reliance when it's above its 200-day average and RSI crosses 50."</p></li>
            <li className="lp-card"><span className="lp-num">2</span><b>Check the rules</b><p className="small muted">Plain-English rules. Tap any highlighted word to change it.</p></li>
            <li className="lp-card"><span className="lp-num">3</span><b>Get the verdict</b><p className="small muted">Years of real prices, real costs and four checks.</p></li>
            <li className="lp-card"><span className="lp-num">4</span><b>Paper trade it</b><p className="small muted">When it holds up, run it live with fake money.</p></li>
          </ol>

          <div id="checks" className="stack lp-anchor g18">
            <h3 className="serif lp-h3">Four questions every strategy has to answer.</h3>
            <div className="lp-checks">
              {CHECKS.map((c) => (
                <div key={c.title} className="lp-card lp-check">
                  <div className="lp-art" aria-hidden="true">{c.art}</div>
                  <b className="serif lp-check-t">{c.title}</b>
                  <p className="small muted">{c.body}</p>
                </div>
              ))}
            </div>
          </div>

          <LibraryExamples />

          <div className="lp-card lp-travel lp-options">
            <div className="stack g6">
              <span className="eyebrow">Options</span>
              <b className="serif lp-opt-title">Paper trade option structures on live prices.</b>
              <p className="small muted k-measure m60">Straddles, strangles, condors or any structure up to eight legs, filled at the real bid and ask. See the Greeks, the payoff today beside the one at expiry, and breakevens after charges.</p>
            </div>
            <span className="lp-tag">No real orders, ever</span>
          </div>

          <ToolList items={TOOLS} label="Trade tools" />

          <div id="markets" className="stack lp-anchor g14">
            <h3 className="serif lp-h3">Test where you trade.</h3>
            <p className="lp-p">Each market with its own hours, currency, holidays, fees and taxes.</p>
            <div className="lp-markets">
              {MARKETS.map(([sym, n]) => <div key={n} className="lp-market"><span className="lp-sym" aria-hidden="true">{sym}</span><b>{n}</b></div>)}
            </div>
          </div>
        </div>
      </section>

      <section id="invest" className="lp-sec">
        <div className="lp-wrap stack g36">
          <div className="lp-split">
            <Head eyebrow="Invest · research" title="Start with any company, Indian or US.">
              Reported numbers, exchange filings and the company's own documents. Plain numbers, never scores, ratings or calls on the stock.
            </Head>
            <ResearchMock />
          </div>
          <ToolList items={RESEARCH} label="research tools" />
        </div>
      </section>

      <section id="money" className="lp-sec lp-alt">
        <div className="lp-wrap stack g32">
          <Head eyebrow="Money" title="What you own, and what it means at tax time.">
            Bring the files you already have. StratLab keeps them private and reports facts and arithmetic about what you own.
          </Head>
          {/* eight in view (two full rows of four, four of two on a phone), the rest one click away */}
          <div className="stack">
            <div className="lp-money">{PORTFOLIO.slice(0, 8).map(moneyCard)}</div>
            <details className="lp-more">
              <summary>{PORTFOLIO.length - 8} more Money tools</summary>
              <div className="lp-money">{PORTFOLIO.slice(8).map(moneyCard)}</div>
            </details>
          </div>
        </div>
      </section>

      <section id="alerts" className="lp-sec">
        <div className="lp-wrap stack g32">
          <Head eyebrow="Alerts" title="Hear about it when it happens.">
            On your phone, on Telegram or by email, including every paper trade. Alerts report what happened, never what to do about it.
          </Head>
          <ToolList items={ALERTS} label="kinds of alert" shown={3} three />
        </div>
      </section>

      <Pricing />

      <section id="faq" className="lp-sec lp-alt">
        <div className="lp-wrap lp-split lp-split-top">
          <Head eyebrow="Questions" title="Good to know.">
            Anything not answered here, the Contact page at the bottom reaches a person.
          </Head>
          <div className="lp-faq">
            {FAQ.map((f) => <details key={f.q}><summary>{f.q}</summary>{f.a.map((t) => <p key={t} className="muted">{t}</p>)}</details>)}
          </div>
        </div>
      </section>

      <section className="lp-final ruled">
        <div className="lp-wrap stack g20 lp-center">
          <p className="serif lp-h2 lp-final-h">Test it, research it, track it.</p>
          <p className="lp-p">Sign in with Google, no card needed. Your home page shows the first steps.</p>
          {cta("Continue with Google")}
        </div>
      </section>
      </main>

      <footer className="lp-foot">
        <div className="lp-wrap spread wrap g16">
          <Logo size={30} />
          <p className="small muted k-measure">Research and paper trading only. No real orders are placed. Past results don't predict future returns, and nothing on StratLab is investment advice. © {new Date().getFullYear()} StratLab.</p>
          <LegalLinks />
        </div>
      </footer>
    </div>
  );
}

/** The three plans, priced in the visitor's currency (rupees in India), with the same lines as the Plans page. One look in
 * every case: while the prices are coming the cards are drawn with their amounts held back (so nothing flashes rupees and
 * then changes, and nothing moves), and if they can't be read the cards show the rupee prices with a line saying so. */
function Pricing() {
  const { pricing, currency, status } = usePricing();
  const loading = status === "loading";
  // what's on sale today comes from the server (plans.offer_state), the same answer the Plans page reads
  const offer = pricing?.offer ?? null;
  const local = currency !== "INR" ? pricing?.currencies[currency] : undefined;
  const buy = canBuy(offer);
  const rupees = (p: PlanId, year = false) => `₹${PRICE[p][year ? 1 : 0].toLocaleString("en-IN")}`;
  /** The amount in the visitor's currency: the admin price table's ($8 and $20 for dollars). */
  const amount = (p: PlanId, year = false): number => {
    if (p === "free") return 0;
    if (!local) return PRICE[p][year ? 1 : 0];
    return (local as unknown as Record<string, number>)[year ? `${p}_year` : p];
  };
  const price = (p: PlanId, year = false) => (local ? money(local, amount(p, year), currency) : rupees(p, year));
  const intro = pricingIntro(offer, LIMITS.pro, "landing");
  const [period, setPeriod] = useState<"month" | "year">("month");
  const yearly = (p: PlanId) => price(p, true);
  const small = finePrint(offer, { currency: local ? currency : "INR", inRupees: local?.charged_in === "INR", inRupeesYear: local?.yearly_charged_in === "INR",
    year: { basic: yearly("basic"), pro: yearly("pro") }, charged: { basic: rupees("basic"), pro: rupees("pro") } });
  const showYear = !!(offer?.yearly && offer.payments);
  return (
    <section id="pricing" className="lp-sec" aria-busy={loading}>
      <div className="lp-wrap stack g32">
        {loading ? (
          <div className="lp-head lp-head-skel"><span className="eyebrow">Plans</span><span className="lp-skel lp-skel-h" /><span className="lp-skel lp-skel-p" /></div>
        ) : <Head eyebrow="Plans" title={intro.title}>{intro.lede}</Head>}
        {/* yearly only where it can be bought: a yearly price nobody can pay would be one more contradiction. The row keeps its height either way. */}
        <div className="lp-period">
          {showYear && !loading ? (
            <Seg label="Billing period" value={period} onChange={(v) => setPeriod(v as "month" | "year")}
              options={[{ value: "month", label: "Monthly" }, { value: "year", label: YEARLY_LABEL }]} />
          ) : loading ? <span className="lp-skel lp-skel-seg" /> : <span className="small muted">Prices are per month</span>}
        </div>
        <div className="lp-prices">
          {PLAN_IDS.map((p) => {
            const year = showYear && period === "year" && p !== "free";
            const act = landingAction(offer, p);
            const per = year ? "year" : "month";
            // the amount a card is really charged, when it is not the amount shown (a currency that is charged in rupees)
            const chargedInRupees = p !== "free" && !!local && (year ? local.yearly_charged_in : local.charged_in) === "INR";
            const save = p !== "free" && year ? yearlySaving(amount(p), amount(p, true)) : null;
            return (
              <div key={p} className={`lp-card lp-price${p === "pro" ? " lp-price-top" : ""}`} data-plan={p}>
                <div className="stack g2">
                  <h3 className="h2">{PLAN_NAME[p]}</h3>
                  <span className="small muted">{WHO[p]}</span>
                </div>
                <div className="stack g2">
                  {loading ? <span className="lp-skel lp-skel-amount" aria-label="Loading the price" /> : (
                    <div className="serif lp-amount">{price(p, year)}<span className="small muted"> / {per}</span></div>
                  )}
                  {p !== "free" && (
                    <span className="small lp-price-note">
                      {loading ? <span className="lp-skel lp-skel-note" />
                        : chargedInRupees ? `${buy ? "Charged as" : "Will be charged as"} ${rupees(p, year)} / ${per} incl. GST`
                        : local ? "" : "incl. GST"}
                      {!loading && save != null && <span className="lp-save">{`Saves ${money(local, save, currency)} a year against paying monthly`}</span>}
                    </span>
                  )}
                </div>
                {"note" in act ? <span className="lp-plan-note small muted">{act.note}</span>
                  : <button type="button" className={`btn ${p === "pro" ? "" : "outline"}`} disabled={loading} onClick={() => void signIn(act.buy ? "/plans" : null)}>{act.label}</button>}
                <ul className="lp-plan-list">
                  {FEATURES[p].map((f) => f.endsWith(":") ? <li key={f} className="small muted lp-plan-sub">{f}</li>
                    : <li key={f}><span aria-hidden="true">✓</span>{f}</li>)}
                </ul>
              </div>
            );
          })}
        </div>
        {loading ? <span className="lp-skel lp-skel-fine" /> : small.length > 0 && <p className="small muted k-measure m80">{small.join(" ")}</p>}
      </div>
    </section>
  );
}

/** Idea → rules → verdict, cycling through three examples until someone picks one. All three are laid on top of one
 * another, so the card is always as tall as the tallest and nothing around it moves when the example changes. The tabs
 * follow the usual keyboard pattern: one tab stop, the arrow keys move between them. */
function HeroDemo() {
  const [i, setI] = useState(0);
  const [auto, setAuto] = useState(true);
  const [paused, setPaused] = useState(false);
  const base = useId();
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  useEffect(() => {
    if (!auto || paused || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t = setInterval(() => setI((x) => (x + 1) % DEMOS.length), 6000);
    return () => clearInterval(t);
  }, [auto, paused]);
  const pick = (k: number, focus = false) => { setI(k); setAuto(false); if (focus) tabs.current[k]?.focus(); };
  const onKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    const to = e.key === "ArrowRight" || e.key === "ArrowDown" ? (i + 1) % DEMOS.length
      : e.key === "ArrowLeft" || e.key === "ArrowUp" ? (i + DEMOS.length - 1) % DEMOS.length
      : e.key === "Home" ? 0 : e.key === "End" ? DEMOS.length - 1 : -1;
    if (to < 0) return;
    e.preventDefault();
    pick(to, true);
  };
  return (
    <div className="lp-demo" role="group" aria-label="Example: an idea, its rules and its result"
      onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)} onFocus={() => setPaused(true)} onBlur={() => setPaused(false)}>
      <div className="lp-demo-tabs" role="tablist" aria-label="Example ideas">
        {DEMOS.map((x, k) => (
          <button key={x.tab} ref={(el) => { tabs.current[k] = el; }} type="button" role="tab" id={`${base}-t${k}`} aria-controls={`${base}-p${k}`}
            aria-selected={k === i} tabIndex={k === i ? 0 : -1} onKeyDown={onKey} onClick={() => pick(k)}>{x.tab}</button>
        ))}
      </div>
      <div className="lp-demo-stack">
        {DEMOS.map((d, k) => (
          <div key={d.tab} role="tabpanel" id={`${base}-p${k}`} aria-labelledby={`${base}-t${k}`} className={`lp-demo-body${k === i ? " on" : " off"}`}>
            <div className="lp-card lp-demo-idea">
              <span className="eyebrow">You write</span>
              <p className="serif">"{d.idea}"</p>
            </div>
            <div className="lp-card lp-demo-rule">
              <span className="eyebrow">StratLab reads</span>
              <p>{d.rule.map(([w, tok], n) => tok ? <span key={n} className="lp-tok">{w}</span> : <span key={n}> {w} </span>)}</p>
            </div>
            <div className="lp-card lp-demo-verdict">
              <div className="spread g8"><span className="eyebrow">{d.meta}</span><span className="lp-sample">Sample result</span></div>
              <span className={`serif lp-verdict tone-${d.tone}`}>{d.verdict}</span>
              <p className="serif lp-why">{d.why}</p>
              <div className="stack small lp-checklist">
                {d.checks.map(([t, s]) => <div key={t} className="spread"><span>{t}</span><span className={`badge ${s}`}>{STATUS[s]}</span></div>)}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** What every made-up picture on the landing page says about itself, in readable type. A real company or asset beside
 * invented numbers would contradict its own public page, so the pictures name no real company, ticker or date. */
const ILLUSTRATION = "Illustration: made-up figures";

/** A small picture of each space as it looks inside, so the three choices show, not tell. */
function SpaceArt({ space }: { space: string }) {
  if (space === "trade") return (
    <div className="lp-space-art" aria-hidden="true">
      <span className="lp-illus">{ILLUSTRATION}</span>
      <span className="tiny muted mono">An RSI idea · 61 trades</span>
      <span className="serif lp-space-big">Held up on unseen years.</span>
      <span className="row wrap g4">
        {(["pass", "pass", "warn", "pass"] as Status[]).map((st, k) => <span key={k} className={`badge ${st}`}>{["Unseen", "Nearby", "Drawdown", "Trades"][k]}</span>)}
      </span>
    </div>
  );
  if (space === "invest") return (
    <div className="lp-space-art" aria-hidden="true">
      <span className="lp-illus">{ILLUSTRATION}</span>
      <span className="tiny muted mono">Sample Industries · a made-up company</span>
      <span className="lp-space-rows">
        <span><span className="muted">Sales, 3 years</span><b className="num">+11.2% a year</b></span>
        <span><span className="muted">Debt to equity</span><b className="num">0.41</b></span>
        <span><span className="muted">Next results</span><b className="num">in 12 days</b></span>
      </span>
    </div>
  );
  return (
    <div className="lp-space-art" aria-hidden="true">
      <span className="lp-illus">{ILLUSTRATION}</span>
      <span className="tiny muted mono">My Holdings · 6 stocks</span>
      <span className="lp-space-rows">
        <span><span className="muted">Value</span><b className="num">₹7,10,215</b></span>
        <span><span className="muted">Gain or loss</span><b className="num lp-blue">+₹4,49,403</b></span>
        <span><span className="muted">Tax this year (estimate)</span><b className="num">₹12,480</b></span>
      </span>
    </div>
  );
}

function ResearchMock() {
  // what a company page's AI read looks like: plain numbers from reported results and prices, never scores. The company,
  // its ticker and every figure are made up, and the card says so where it can't be missed (no live quote, no day's change)
  const facts: [string, string][] = [["Growth", "Sales, 3 years 68.2% a year · Net profit, 3 years 91.4% a year"],
    ["Price trend", "6.1% above the 200-day average · 1-year change +32.5% · Stage 2 (advancing)"],
    ["Debt and cash", "Debt to equity 0.11 · Cash from operations 94% of net profit"],
    ["Margins and returns", "EBITDA margin 33% → 62% over 5 years · ROE 41.9%"]];
  return (
    <div className="lp-card lp-rmock" aria-label="Illustration of a company research page: a made-up company with made-up figures">
      <span className="lp-illus">Illustration: a made-up company and made-up figures</span>
      <div className="spread lp-top">
        <div className="stack g2"><span className="eyebrow">SAMPLE · made-up ticker</span><b className="serif lp-rm-title">Sample Motors Inc.</b></div>
        <div className="stack g4 lp-end"><b className="serif lp-rm-title">$183.20</b><span className="badge next">Last close ▲ 1.33%</span></div>
      </div>
      <div className="lp-rfacts">
        {facts.map(([l, t]) => <div key={l} className="stack g1"><b className="small">{l}</b><span className="small muted">{t}</span></div>)}
        <span className="small lp-illus-note">Facts from reported results and prices, never advice. A real company's page shows its own numbers.</span>
      </div>
      <div className="lp-ridea">
        <b className="small">A rule template to test</b>
        <p className="small">"Enter when the 20-day EMA crosses above the 50-day EMA; exit when it crosses back below; 7% stop loss."</p>
        <span className="small muted">A template for a test, not a suggestion. The test shows how it would have done on past prices.</span>
        <button type="button" className="btn sm lp-idea-btn" onClick={() => void signIn("/new")}>Continue with Google to test it →</button>
      </div>
    </div>
  );
}

/** A few of StratLab's own library strategies with the verdict each earned: real output anyone can open without signing in.
 * One of each kind of verdict where there is one (the ones that failed are shown like the ones that held up), up to three. */
function LibraryExamples() {
  const [rows, setRows] = useState<LibEntry[] | null>(null);
  const [total, setTotal] = useState(0);
  useEffect(() => {
    let live = true;
    publicGet<{ entries: LibEntry[]; total: number }>("/public/library?sort=new&limit=60")
      .then((r) => { if (!live) return; const seen = new Set<string>(); setTotal(r.total); setRows(r.entries.filter((e) => e.ran !== false && !seen.has(e.verdict.verdict) && !!seen.add(e.verdict.verdict)).slice(0, 3)); })
      .catch(() => { if (live) setRows([]); });
    return () => { live = false; };
  }, []);
  if (rows && rows.length === 0) return null;          // nothing published (or the list couldn't be read): no heading over an empty space
  return (
    <div id="examples" className="stack lp-anchor g14">
      <h3 className="serif lp-h3">Real verdicts, open to read.</h3>
      <p className="lp-p">StratLab's own strategies, run through the same test and four checks. Each shows its rules and the verdict it earned, the failures as plainly as the rest.</p>
      {rows === null ? <div className="lp-examples lp-examples-skel" aria-busy="true"><span className="lp-skel lp-skel-card" /><span className="lp-skel lp-skel-card" /><span className="lp-skel lp-skel-card" /></div>
        : rows.length > 0 && (
          <div className="lp-examples">
            {rows.map((e) => (
              <Link key={e.id} to={`/library/${encodeURIComponent(e.id)}`} className="lp-card lp-example">
                <span className="eyebrow">{e.group ? e.group.name : e.instrument?.symbol ?? e.market}</span>
                <b className="serif">{plainTerms(e.name)}</b>
                <span className="small">{e.verdict.fact_headline ?? e.verdict.headline}</span>
                <span className="small muted">{checksLine(e.verdict.passed, e.verdict.total)}</span>
                <span className="small lp-space-go">Open the verdict and rules →</span>
              </Link>
            ))}
          </div>
        )}
      <p><Link className="link" to="/library">{total > 1 ? `See all ${total} StratLab strategies` : "See StratLab's strategy"} and the verdict each earned</Link></p>
    </div>
  );
}

/* small illustrations for the four checks */
function ArtUnseen() {
  // the label is page text (readable at any size), not a drawn 8px one
  return (
    <>
      <svg viewBox="0 0 200 80">
        <rect x="140" y="4" width="56" height="72" rx="6" fill="var(--orange-soft)" />
        <polyline points="6,66 26,58 46,60 66,46 86,44 106,32 126,26 140,24" fill="none" stroke="var(--blue)" strokeWidth="2.5" strokeLinejoin="round" />
        <polyline points="140,24 156,34 170,30 184,48 196,56" fill="none" stroke="var(--orange)" strokeWidth="2.5" strokeLinejoin="round" />
      </svg>
      <span className="lp-art-tag">Unseen</span>
    </>
  );
}
function ArtNearby() {
  const cells = [0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 2, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0];
  return (
    <svg viewBox="0 0 200 80">
      {cells.map((c, k) => (
        <rect key={k} x={52 + (k % 5) * 20} y={2 + Math.floor(k / 5) * 15.5} width="17" height="13" rx="3"
          fill={c === 2 ? "var(--blue)" : c === 1 ? "var(--chip)" : "var(--orange-soft)"} stroke={c === 2 ? "var(--ink)" : "none"} />
      ))}
    </svg>
  );
}
function ArtDrawdown() {
  const paths = ["6,20 40,28 80,24 120,40 160,34 196,44", "6,20 40,34 80,40 120,36 160,52 196,48", "6,20 40,30 80,46 120,58 160,54 196,62", "6,20 40,26 80,30 120,28 160,40 196,36"];
  return (
    <svg viewBox="0 0 200 80">
      {paths.map((p, k) => <polyline key={k} points={p} fill="none" stroke={k === 2 ? "var(--orange)" : "var(--dash)"} strokeWidth={k === 2 ? 2.5 : 1.5} />)}
      <line x1="6" y1="72" x2="196" y2="72" stroke="var(--line-2)" strokeDasharray="3 3" />
    </svg>
  );
}
function ArtTrades() {
  return (
    <svg viewBox="0 0 200 80">
      {Array.from({ length: 30 }, (_, k) => (
        <circle key={k} cx={14 + (k % 10) * 19} cy={16 + Math.floor(k / 10) * 22} r="6.5" fill={k < 5 ? "var(--blue)" : "var(--chip)"} />
      ))}
    </svg>
  );
}
