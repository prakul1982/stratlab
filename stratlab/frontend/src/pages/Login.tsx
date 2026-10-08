import { useEffect, useState, type JSX, type ReactNode } from "react";
import { money, usePricing } from "../lib/currency";
import { finePrint, landingAction, pricingIntro } from "../lib/offer";
import { FEATURES, LIMITS, PLAN_IDS, PLAN_NAME, PRICE, WHO, type PlanId } from "../lib/plans";
import { signIn } from "../lib/signin";
import { Google } from "../components/Icons";
import { LegalLinks } from "../components/LegalLinks";
import { Logo } from "../components/Logo";
import { Seg } from "../components/kit/Seg";

/* The public landing page: what StratLab does, in its three spaces (Trade, the strategy lab it began as, first; then
 * Invest and Money), the alerts across them, the plans, and one way in (Google sign-in). */

type Status = "pass" | "warn" | "fail";
const STATUS: Record<Status, string> = { pass: "Passed", warn: "Warning", fail: "Failed" };

/** Three sample ideas for the hero demo: what you write, how it's read, what the verdict says. */
const DEMOS: {
  tab: string; idea: string; rule: [string, boolean][]; meta: string; verdict: string; tone: "blue" | "orange" | "ink"; why: string; checks: [string, Status][];
}[] = [
  {
    tab: "NIFTY 50", idea: "Buy NIFTY 50 when the 20-day average crosses above the 50-day, with a 2% stop loss",
    rule: [["Buy when", false], ["SMA 20", true], ["crosses above", true], ["SMA 50", true], ["· stop loss", false], ["2%", true]],
    meta: "Experiment v3 · NIFTY 50 · 38 trades", verdict: "Probably luck.", tone: "orange",
    why: "It made money on the years it was tuned on, then lost on years it had never seen.",
    checks: [["Unseen data", "fail"], ["Nearby settings", "fail"], ["Bad-luck drawdown", "warn"], ["Enough trades", "pass"]],
  },
  {
    tab: "Bitcoin", idea: "Buy Bitcoin when RSI drops below 30, sell when it goes back above 55",
    rule: [["Buy when", false], ["RSI 14", true], ["falls below", true], ["30", true], ["· sell when above", false], ["55", true]],
    meta: "Experiment v5 · BTC/USD · 61 trades", verdict: "Likely a real edge.", tone: "blue",
    why: "It kept working on data it had never seen, and small changes to the settings didn't break it.",
    checks: [["Unseen data", "pass"], ["Nearby settings", "pass"], ["Bad-luck drawdown", "warn"], ["Enough trades", "pass"]],
  },
  {
    tab: "NVIDIA", idea: "Short NVDA when it falls below its 20-day low, with a 5% trailing stop",
    rule: [["Sell short when", false], ["price", true], ["falls below", true], ["20-day low", true], ["· trail the stop", false], ["5%", true]],
    meta: "Experiment v1 · NVDA · 9 trades", verdict: "Not enough evidence.", tone: "ink",
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
  ["Trade journal", "Your real trades as round trips after charges, with the same honesty checks."],
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

/** The questions people ask before signing up, kept to the few that decide it. Plan details are in Pricing above. */
const FAQ: [string, string][] = [
  ["Does StratLab tell me what to buy?", "No. It shows facts: reported numbers, filings, prices and how a set of rules would have done in the past. It never says buy, sell or hold, gives no price targets or ratings, and nothing on StratLab is investment advice."],
  ["Does StratLab place real trades?", "No. Testing is on past prices and paper trading uses fake money. No real orders are ever placed."],
  ["Do I need to know how to code?", "No. You describe the idea in plain words. If something is missing, like when to sell, StratLab asks. You can also tap any rule to change it."],
  ["Why not just look at the backtest return?", "Because almost any idea can be tuned to look great on past prices. The honesty checks ask whether it would have worked on data it never saw, with slightly different settings, and with worse luck. That's the difference between an edge and a coincidence."],
  ["Who can see my money data?", "Only you. Your holdings, funds, net worth, trades and tax figures are kept per account, never shown to anyone else, and each page deletes its data in one step. A mutual fund statement and its password are read once and not stored."],
  ["Does StratLab file my tax return?", "No. The tax report is an estimate to check with a chartered accountant, and the ITR-ready export lays out your year the way the ITR-2 and ITR-3 schedules ask for it. You or your CA file the return."],
  ["Can I test options strategies?", "You can paper trade them live on NSE, BSE, MCX and NSE currency option prices, with fills at the real bid and ask, at a set time or when a notebook's rules signal. Backtesting options needs real past prices for every strike, so StratLab records the NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY and SENSEX chains every 5 minutes to build that history rather than guess with a pricing model. The Greeks and the payoff before expiry are model estimates, labelled with their inputs."],
  ["How do invite rewards work?", "Invite friends, both get a month of Basic. Your invite link is in Account. When a friend joins with your link and uses StratLab on 3 different days in their first 2 weeks, they get a month of Basic free. You get a free month for each of your first 2 friends who do this each year, and for each of your first 2 friends who subscribe. After that, every friend who subscribes gives you 25% off a month (about a week extra). If you already pay, your free time is kept and starts if your paid plan ever stops."],
  ["Is there an app?", "StratLab installs from the browser: on Android or a computer choose Install app, on an iPhone tap Share, then Add to Home Screen. It opens full screen with its own icon and sends alerts as notifications."],
];

const SECTIONS: [string, string][] = [["trade", "Trade"], ["invest", "Invest"], ["money", "Money"],
  ["alerts", "Alerts"], ["pricing", "Pricing"], ["faq", "FAQ"]];

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

/** `section`: scroll there first (the page was opened as /pricing, /help…). */
export function Login({ section = null }: { section?: string | null } = {}) {
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (section) document.getElementById(section)?.scrollIntoView(); }, [section]);

  useEffect(() => {
    const p = new URLSearchParams(location.search + "&" + location.hash.replace(/^#/, ""));
    const d = p.get("error_description");
    if (!d) return;
    setError(/exchange external code/i.test(d)
      ? "Google sign-in couldn't finish: the Google Client ID or Secret saved in Supabase doesn't match your Google Cloud OAuth client."
      : `Sign-in failed: ${d}`);
    history.replaceState(null, "", location.pathname);
  }, []);

  const cta = (label = "Start free") => (
    <button className="btn lp-cta" onClick={() => signIn()}><Google />{label}</button>
  );

  return (
    <div className="lp">
      <header className="lp-nav">
        <a href="#top" className="brand" aria-label="StratLab home"><Logo size={46} /></a>
        <nav aria-label="Sections">
          {SECTIONS.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}
        </nav>
        {/* on a phone the section links fold into a small menu (the row above hides there) */}
        <details className="lp-menu">
          <summary aria-label="Sections menu">Menu</summary>
          <nav aria-label="Sections (menu)" onClick={(e) => { if ((e.target as HTMLElement).closest("a")) (e.currentTarget.parentElement as HTMLDetailsElement).open = false; }}>
            {SECTIONS.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}
          </nav>
        </details>
        <button className="btn outline sm" onClick={() => signIn()}>Sign in</button>
      </header>

      <main>
      <section id="top" className="lp-hero ruled">
        <div className="lp-wrap lp-hero-grid">
          <div className="stack g22">
            <span className="eyebrow">Trade · Invest · Money · Indian and US stocks</span>
            <h1 className="serif lp-h1"><em>Test</em> it, research it, track it.</h1>
            <p className="serif lp-lede">One place for trading ideas, company research and your own money. Facts and honest tests, never tips.</p>
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
          <Head eyebrow="Trade · the strategy lab" title="From a sentence to an honest verdict.">
            Most backtests are tuned until the curve looks good. StratLab tests the idea on real prices after real costs, then checks whether the result holds up.
          </Head>
          <ol className="lp-steps">
            <li className="lp-card"><span className="lp-num">1</span><b>Describe it</b><p className="small muted">"Buy Reliance when it's above its 200-day average and RSI crosses 50."</p></li>
            <li className="lp-card"><span className="lp-num">2</span><b>Check the rules</b><p className="small muted">Plain-English rules. Tap any highlighted word to change it.</p></li>
            <li className="lp-card"><span className="lp-num">3</span><b>Get the verdict</b><p className="small muted">Years of real prices, real costs and four honesty checks.</p></li>
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
            {FAQ.map(([q, a]) => <details key={q}><summary>{q}</summary><p className="muted">{a}</p></details>)}
          </div>
        </div>
      </section>

      <section className="lp-final ruled">
        <div className="lp-wrap stack g20 lp-center">
          <h2 className="serif lp-h2 lp-final-h">Find out before your money does.</h2>
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

/** The three plans, priced in the visitor's currency (rupees in India), with the same lines as the Plans page. */
function Pricing() {
  const { pricing, currency } = usePricing();
  // what's on sale today comes from the server (plans.offer_state), the same answer the Plans page reads
  const offer = pricing?.offer ?? null;
  const local = currency !== "INR" ? pricing?.currencies[currency] : undefined;
  const rupees = (p: PlanId, year = false) => `₹${PRICE[p][year ? 1 : 0].toLocaleString("en-IN")}`;
  /** The amount in the visitor's currency: the admin price table's ($8 and $20 for dollars). */
  const price = (p: PlanId, year = false) => {
    if (!local) return { shown: rupees(p, year) };
    if (p === "free") return { shown: money(local, 0, currency) };
    const v = (local as unknown as Record<string, number>)[year ? `${p}_year` : p];
    return { shown: money(local, v, currency) };
  };
  const intro = pricingIntro(offer, LIMITS.pro, "landing");
  const [period, setPeriod] = useState<"month" | "year">("month");
  const yearly = (p: PlanId) => price(p, true).shown;
  const small = finePrint(offer, { currency: local ? currency : "INR", inRupees: local?.charged_in === "INR", inRupeesYear: local?.yearly_charged_in === "INR",
    year: { basic: yearly("basic"), pro: yearly("pro") }, charged: { basic: rupees("basic"), pro: rupees("pro") } });
  return (
    <section id="pricing" className="lp-sec">
      <div className="lp-wrap stack g32">
        <Head eyebrow="Pricing" title={intro.title}>{intro.lede}</Head>
        {/* yearly only where it can be bought: a yearly price nobody can pay would be one more contradiction */}
        {offer?.yearly && offer.payments && (
          <Seg label="Billing period" value={period} onChange={(v) => setPeriod(v as "month" | "year")}
            options={[{ value: "month", label: "Monthly" }, { value: "year", label: "Yearly · 2 months free" }]} />
        )}
        <div className="lp-prices">
          {PLAN_IDS.map((p) => {
            const year = period === "year" && p !== "free";
            const pr = price(p, year);
            const act = landingAction(offer, p);
            return (
              <div key={p} className={`lp-card lp-price${p === "pro" ? " lp-price-top" : ""}`} data-plan={p}>
                <div className="stack g2">
                  <h3 className="h2">{PLAN_NAME[p]}</h3>
                  <span className="small muted">{WHO[p]}</span>
                </div>
                <div className="stack g2">
                  <div className="serif lp-amount">{pr.shown}<span className="small muted"> / {year ? "year" : "month"}</span></div>
                  {p !== "free" && <span className="tiny muted">{local ? `${rupees(p, year)} a ${year ? "year" : "month"} in India, incl. GST` : "incl. GST"}</span>}
                </div>
                {"note" in act ? <span className="lp-plan-note small muted">{act.note}</span>
                  : <button type="button" className={`btn ${p === "pro" ? "" : "outline"}`} onClick={() => void signIn(act.buy ? "/plans" : null)}>{act.label}</button>}
                <ul className="lp-plan-list">
                  {FEATURES[p].map((f) => f.endsWith(":") ? <li key={f} className="small muted lp-plan-sub">{f}</li>
                    : <li key={f}><span aria-hidden="true">✓</span>{f}</li>)}
                </ul>
              </div>
            );
          })}
        </div>
        {small.length > 0 && <p className="small muted k-measure m80">{small.join(" ")}</p>}
      </div>
    </section>
  );
}

/** Idea → rules → verdict, cycling through three examples until someone picks one. */
function HeroDemo() {
  const [i, setI] = useState(0);
  const [auto, setAuto] = useState(true);
  useEffect(() => {
    if (!auto || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t = setInterval(() => setI((x) => (x + 1) % DEMOS.length), 6000);
    return () => clearInterval(t);
  }, [auto]);
  const d = DEMOS[i];
  return (
    <div className="lp-demo" aria-label="Example: an idea, its rules and its verdict">
      <div className="lp-demo-tabs" role="tablist">
        {DEMOS.map((x, k) => (
          <button key={x.tab} role="tab" aria-selected={k === i} aria-pressed={k === i} onClick={() => { setI(k); setAuto(false); }}>{x.tab}</button>
        ))}
      </div>
      <div key={i} className="lp-demo-body">
        <div className="lp-card lp-demo-idea">
          <span className="eyebrow">You write</span>
          <p className="serif">"{d.idea}"</p>
        </div>
        <div className="lp-card lp-demo-rule">
          <span className="eyebrow">StratLab reads</span>
          <p>{d.rule.map(([w, tok], k) => tok ? <span key={k} className="lp-tok">{w}</span> : <span key={k}> {w} </span>)}</p>
        </div>
        <div className="lp-card lp-demo-verdict">
          <span className="eyebrow">{d.meta}</span>
          <span className={`serif lp-verdict tone-${d.tone}`}>{d.verdict}</span>
          <p className="serif lp-why">{d.why}</p>
          <div className="stack small lp-checklist">
            {d.checks.map(([t, s]) => <div key={t} className="spread"><span>{t}</span><span className={`badge ${s}`}>{STATUS[s]}</span></div>)}
          </div>
          <span className="tiny muted">Sample result</span>
        </div>
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
      <span className="serif lp-space-big">Likely a real edge.</span>
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
        <b className="small">Ideas to test</b>
        <p className="small">"Buy when the 20-day EMA crosses above the 50-day EMA, sell when it crosses back below, 7% stop loss"</p>
        <button type="button" className="btn sm lp-idea-btn" onClick={() => void signIn("/new")}>Test an idea like this →</button>
      </div>
    </div>
  );
}

/* small illustrations for the four checks */
function ArtUnseen() {
  return (
    <svg viewBox="0 0 200 80">
      <rect x="140" y="4" width="56" height="72" rx="6" fill="var(--orange-soft)" />
      <text x="168" y="16" textAnchor="middle" fontSize="8" fill="var(--orange-ink)" fontFamily="var(--mono)">UNSEEN</text>
      <polyline points="6,66 26,58 46,60 66,46 86,44 106,32 126,26 140,24" fill="none" stroke="var(--blue)" strokeWidth="2.5" strokeLinejoin="round" />
      <polyline points="140,24 156,34 170,30 184,48 196,56" fill="none" stroke="var(--orange)" strokeWidth="2.5" strokeLinejoin="round" />
    </svg>
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
