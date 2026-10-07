import { lazy, StrictMode, Suspense, useCallback, useEffect, useState, type ComponentType, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import "@fontsource/montserrat/300.css";
import "@fontsource/montserrat/800.css";
import "@fontsource/fraunces/400.css";
import "@fontsource/fraunces/600.css";
import "@fontsource/fraunces/400-italic.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./styles.css";
import "./styles-invest.css";
import { AppProvider, useApp } from "./lib/app";
import { SESSION_KEY } from "./lib/api";
import { takeNext } from "./lib/returnTo";
import { isAppPath, landingSection } from "./lib/deepLinks";
import { registerPwa } from "./lib/pwa";
import { captureRef } from "./lib/share";
import { pageview } from "./lib/analytics";
import { Shell } from "./components/Shell";
import { PageLock } from "./components/PageLock";
import { Loading, Toast } from "./components/ui";
import { LEGAL_PAGES } from "./components/LegalLinks";
import { SPACE_HOMES } from "./lib/spaces";
import { fmtDate } from "./lib/format";

// every page loads when it's opened, so the first visit only downloads the page it shows
const page = <K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) =>
  lazy(() => load().then((m) => ({ default: m[name] })));
const home = () => import("./pages/Home");
const spaceHomes = () => import("./pages/SpaceHomes");
const SpaceHome = page(spaceHomes, "SpaceHome");
const TradeHome = page(spaceHomes, "TradeHome");
const mineHome = () => import("./pages/MineHome");
const MineHome = page(mineHome, "MineHome");
const navPages = () => import("./pages/NavPages");
const GroupPage = page(navPages, "GroupPage");
const FeaturesPage = page(navPages, "FeaturesPage");
const InvestHome = page(spaceHomes, "InvestHome");
const MoneyHome = page(spaceHomes, "MoneyHome");
const NotebooksHome = page(home, "NotebooksHome");
const NewNotebook = page(home, "NewNotebook");
const login = () => import("./pages/Login");
const Login = lazy(() => login().then((m) => ({ default: m.Login })));
// signed out on an app address, a page that doesn't exist, one that isn't yours, and Help
const gate = () => import("./pages/Gate");
const SignInGate = page(gate, "SignInGate");
const NotFound = lazy(() => gate().then((m) => ({ default: m.NotFound })));
const NoAccess = lazy(() => gate().then((m) => ({ default: m.NoAccess })));
const HelpPage = page(gate, "HelpPage");
const legal = () => import("./pages/LegalPage");
const LegalPage = page(legal, "LegalPage");
const notebook = () => import("./pages/NotebookPage");
const NotebookPage = page(notebook, "NotebookPage");
const experiment = () => import("./pages/ExperimentPage");
const ExperimentPage = page(experiment, "ExperimentPage");
const MarketPage = page(() => import("./pages/MarketPage"), "MarketPage");
const OptionsPage = page(() => import("./pages/OptionsPage"), "OptionsPage");
const PositioningPage = page(() => import("./pages/PositioningPage"), "PositioningPage");
const ImportPage = page(() => import("./pages/ImportPage"), "ImportPage");
const verdict = () => import("./pages/PublicVerdict");
const PublicVerdict = page(verdict, "PublicVerdict");
const OptionsSession = page(() => import("./pages/OptionsSession"), "OptionsSession");
const PaperPage = page(() => import("./pages/PaperPage"), "PaperPage");
const ReplayPage = page(() => import("./pages/trade/ReplayPage"), "ReplayPage");
const SignalsPage = page(() => import("./pages/trade/SignalsPage"), "SignalsPage");
const PlansPage = page(() => import("./pages/PlansPage"), "PlansPage");
const AccountPage = page(() => import("./pages/AccountPage"), "AccountPage");
// Account and Settings step 3a: the pages that used to be sections of Account
const SettingsPage = page(() => import("./pages/SettingsPage"), "SettingsPage");
const AssistantPage = page(() => import("./pages/AssistantPage"), "AssistantPage");
const AppPage = page(() => import("./pages/AppPage"), "AppPage");
const InvitePage = page(() => import("./pages/InvitePage"), "InvitePage");
const AdminPage = page(() => import("./pages/AdminPage"), "AdminPage");
const LibraryPage = page(() => import("./pages/LibraryPage"), "LibraryPage");
const CompareExperiments = page(() => import("./pages/CompareExperiments"), "CompareExperiments");
const research = () => import("./pages/Research");
const ResearchHome = page(research, "ResearchHome");
const ThemesPage = page(research, "ThemesPage");
const PulsePage = page(research, "PulsePage");
const ComparePage = page(research, "ComparePage");
const WatchlistPage = page(research, "WatchlistPage");
const ScanPage = page(research, "ScanPage");
const deep = () => import("./pages/DeepDive");
const DeepDivePage = page(deep, "DeepDivePage");
const investor = () => import("./pages/InvestorHome");
const InvestorHomePage = page(investor, "InvestorHomePage");
const holdingsPage = () => import("./pages/HoldingsPage");
const HoldingsPage = page(holdingsPage, "HoldingsPage");
const taxPage = () => import("./pages/TaxReportPage");
const mfPage = () => import("./pages/money/MutualFundsPage");
const MutualFundsPage = page(mfPage, "MutualFundsPage");
const TaxReportPage = page(taxPage, "TaxReportPage");
const TaxToolsPage = page(() => import("./pages/money/TaxToolsPage"), "TaxToolsPage");
const moneyCalendar = () => import("./pages/money/MoneyCalendarPage");
const MoneyCalendarPage = page(moneyCalendar, "MoneyCalendarPage");
const UsTaxPage = page(() => import("./pages/money/UsTaxPage"), "UsTaxPage");
const ItrExportPage = page(() => import("./pages/money/ItrExportPage"), "ItrExportPage");
const SipTestPage = page(() => import("./pages/money/SipTestPage"), "SipTestPage");
const RatesPage = page(() => import("./pages/money/RatesPage"), "RatesPage");
const news = () => import("./pages/NewsPage");
const NewsPage = page(news, "NewsPage");
const RotationPage = page(research, "RotationPage");
const FilingsPage = page(research, "FilingsPage");
const ResultsPage = page(research, "ResultsPage");
const CorpActionsPage = page(() => import("./pages/CorpActionsPage"), "CorpActionsPage");
const CompanyPage = page(research, "CompanyPage");
const AlertsPage = page(() => import("./pages/AlertsPage"), "AlertsPage");
const screensPage = () => import("./pages/Screens");
const ScreensPage = page(screensPage, "ScreensPage");
const breadthPage = () => import("./pages/BreadthPage");
const BreadthPage = page(breadthPage, "BreadthPage");
const EtfGapsPage = page(() => import("./pages/EtfGapsPage"), "EtfGapsPage");
const HoldersPage = page(() => import("./pages/HoldersPage"), "HoldersPage");
const BizUpdatesPage = page(() => import("./pages/BizUpdatesPage"), "BizUpdatesPage");
const netWorth = () => import("./pages/money/NetWorthPage");
const NetWorthPage = page(netWorth, "NetWorthPage");
const journalPage = () => import("./pages/trade/JournalPage");
const JournalPage = page(journalPage, "JournalPage");
const FoChangesPage = page(() => import("./pages/trade/FoChangesPage"), "FoChangesPage");
const ClosingAuctionPage = page(() => import("./pages/trade/ClosingAuctionPage"), "ClosingAuctionPage");
const EventsPage = page(() => import("./pages/trade/EventsPage"), "EventsPage");
const StockFuturesPage = page(() => import("./pages/trade/StockFuturesPage"), "StockFuturesPage");
const StockLendingPage = page(() => import("./pages/StockLendingPage"), "StockLendingPage");
const MarginFundingPage = page(() => import("./pages/MarginFundingPage"), "MarginFundingPage");
const DevKit = page(() => import("./pages/DevKit"), "DevKit");   // /dev/kit: the design kit on one page (dev builds and admins only)

/** Start downloading the first page's code now, alongside the sign-in check, instead of after it. */
function warmFirstPage(path: string) {
  let saved = false;
  try { saved = !!localStorage.getItem(SESSION_KEY); } catch { /* storage off */ }
  const load = LEGAL_PAGES.some((p) => p.path === path) ? legal
    : path.startsWith("/verdict/") ? verdict
    : !saved ? login
    : /^\/(trade|invest|money)?$/.test(path) ? spaceHomes
    : path === "/mine" ? mineHome
    : /^\/(notebooks|new)$/.test(path) ? home
    : /^\/n\/[^/]+$/.test(path) ? notebook
    : /^\/n\/[^/]+\/e\//.test(path) ? experiment
    : /^\/research\/(IN|US)\/[^/]+\/deep$/.test(path) ? deep
    : path === "/research/investor" ? investor
    : path === "/news" ? news
    : path === "/holdings" ? holdingsPage
    : path === "/tax-report" ? taxPage
    : path === "/money/net-worth" ? netWorth
    : path === "/money/mutual-funds" ? mfPage
    : path === "/money/calendar" ? moneyCalendar
    : path === "/trade/journal" ? journalPage
    : path === "/research/screens" ? screensPage
    : path.startsWith("/research") ? research
    : null;
  load?.().catch(() => undefined);    // only a head start: the page itself reports a failed download
}
warmFirstPage(location.pathname);

/** Indian data is offline: say why in plain words. On a weekend or holiday that's expected, not a fault. */
function DataBanner({ note }: { note: { closed: "weekend" | "holiday" | null; back_at: string | null } | null }) {
  const back = note?.back_at ? new Date(note.back_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false }) : null;
  const others = "Crypto, the other markets and your own data work as usual.";
  if (note?.closed) {
    const why = note.closed === "weekend" ? "closed for the weekend" : "closed today for an exchange holiday";
    return (
      <div className="banner">
        <span>Indian markets are {why}. {back ? `Indian price data reconnects at ${back} your time, so backtests on Indian instruments can run again then.` : "Indian price data reconnects with the next daily login."} {others}</span>
      </div>
    );
  }
  if (back) return <div className="banner"><span>Indian price data reconnects at {back} your time, before the market opens. {others}</span></div>;
  return (
    <div className="banner">
      <span>Indian market data is offline: today's data login hasn't completed. {others}</span>
      <Link to="/settings#check" className="btn sm quiet">Run a connection check</Link>
    </div>
  );
}

/** The launch offer: every Pro feature free for everyone until a date. Dismissed per offer. */
function PromoBanner({ until }: { until: string }) {
  const key = `stratlab.promo.seen.${until.slice(0, 10)}`;
  const [hidden, setHidden] = useState(() => { try { return localStorage.getItem(key) === "1"; } catch { return false; } });
  if (hidden) return null;
  const day = fmtDate(until, { year: false });
  return (
    <div className="banner promo-banner">
      <span><b>Launch offer:</b> every Pro feature is free for everyone until {day}. After that, your plan's limits apply again.</span>
      <button className="btn sm quiet" onClick={() => { try { localStorage.setItem(key, "1"); } catch { /* storage off */ } setHidden(true); }}>Got it</button>
    </div>
  );
}

/** A page only the site's team opens: anyone else is told so, not sent home in silence. */
function AdminOnly({ what, children }: { what: string; children: ReactNode }) {
  const { me } = useApp();
  if (!me) return <Loading label="Checking access" />;
  return me.is_admin ? <>{children}</> : <NoAccess what={what} email={me.email} />;
}

function Routed() {
  const { session, ready, dataOffline, meError, me } = useApp();
  const loc = useLocation();
  const nav = useNavigate();
  useEffect(() => { pageview(loc.pathname); }, [loc.pathname]);    // usage analytics: off without a key
  // back from Google sign-in: open the page the visitor started on (lib/returnTo.ts keeps it to StratLab's own pages)
  const signedIn = !!session;
  useEffect(() => {
    if (!signedIn) return;
    const next = takeNext();
    if (next) nav(next, { replace: true });
  }, [signedIn, nav]);
  // shared verdicts are public: no sign-in needed
  if (LEGAL_PAGES.some((p) => p.path === loc.pathname)) return <Suspense fallback={<Loading label="Opening" />}><LegalPage /></Suspense>;   // policies are public: no sign-in needed
  if (loc.pathname.startsWith("/verdict/")) return <Suspense fallback={<Loading label="Opening the verdict" />}><Routes><Route path="/verdict/:token" element={<PublicVerdict />} /></Routes></Suspense>;
  if (!ready) return <Loading label="Opening StratLab" />;
  if (!session) {
    // signed out: the landing page (at a section for /pricing, /help…), "Sign in to see …" on an app address, else Not found
    const section = landingSection(loc.pathname);
    return (
      <Suspense fallback={<Loading label="Opening StratLab" />}>
        {section !== undefined ? <Login section={section} /> : isAppPath(loc.pathname) ? <SignInGate /> : <NotFound signedIn={false} />}
      </Suspense>
    );
  }
  return (
    <Shell>
      {meError && <div className="banner" role="alert">StratLab couldn't load your account: {meError}</div>}
      {dataOffline && !meError && <DataBanner note={me?.data_note ?? null} />}
      {me?.promo && loc.pathname !== "/" && loc.pathname !== "/plans" && !SPACE_HOMES.includes(loc.pathname) && <PromoBanner until={me.promo.until} />}{/* those show a countdown */}
      <PageLock />{/* a paid feature this plan lacks: said at the top, honestly (the server refuses it either way) */}
      <Suspense fallback={<Loading label="Opening" />}>
      <Routes>
        <Route path="/" element={<SpaceHome />} />
        <Route path="/mine" element={<MineHome />} />
        <Route path="/all" element={<Navigate to="/mine" replace />} />
        <Route path="/features" element={<FeaturesPage />} />
        <Route path="/trade/g/:group" element={<GroupPage />} />
        <Route path="/invest/g/:group" element={<GroupPage />} />
        <Route path="/money/g/:group" element={<GroupPage />} />
        <Route path="/trade" element={<TradeHome />} />
        <Route path="/invest" element={<InvestHome />} />
        <Route path="/money" element={<MoneyHome />} />
        <Route path="/notebooks" element={<NotebooksHome />} />
        <Route path="/new" element={<NewNotebook />} />
        <Route path="/n/:id" element={<NotebookPage />} />
        <Route path="/n/:id/market" element={<MarketPage />} />
        <Route path="/n/:id/compare" element={<CompareExperiments />} />
        <Route path="/n/:id/e/:v" element={<ExperimentPage />} />
        <Route path="/import" element={<ImportPage />} />
        <Route path="/library" element={<LibraryPage />} />
        <Route path="/options" element={<OptionsPage />} />
        <Route path="/trade/positioning" element={<PositioningPage />} />
        <Route path="/trade/positioning/stocks" element={<StockFuturesPage />} />
        <Route path="/options/s/:sid" element={<OptionsSession />} />
        <Route path="/paper" element={<PaperPage />} />
        <Route path="/paper/:sid" element={<PaperPage />} />
        <Route path="/trade/journal" element={<JournalPage />} />
        <Route path="/trade/fo-changes" element={<FoChangesPage />} />
        <Route path="/trade/closing-auction" element={<ClosingAuctionPage />} />
        <Route path="/trade/replay" element={<ReplayPage />} />
        <Route path="/trade/signals" element={<SignalsPage />} />
        <Route path="/trade/signals/:sid" element={<SignalsPage />} />
        <Route path="/trade/events" element={<EventsPage />} />
        <Route path="/plans" element={<PlansPage />} />
        {/* the landing page's addresses, signed in: Plans is the pricing page inside the app, Help has its own page */}
        <Route path="/pricing" element={<Navigate to="/plans" replace />} />
        <Route path="/upgrade" element={<Navigate to="/plans" replace />} />
        <Route path="/help" element={<HelpPage />} />
        <Route path="/account" element={<AccountPage />} />
        {/* Account and Settings step 3a: new routes */}
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/assistant" element={<AssistantPage />} />
        <Route path="/app" element={<AppPage />} />
        <Route path="/invite" element={<InvitePage />} />
        <Route path="/admin/*" element={<AdminOnly what="The admin pages"><AdminPage /></AdminOnly>} />
        <Route path="/news" element={<NewsPage />} />
        <Route path="/holdings" element={<HoldingsPage />} />
        <Route path="/tax-report" element={<TaxReportPage />} />
        <Route path="/money/net-worth" element={<NetWorthPage />} />
        <Route path="/money/mutual-funds" element={<MutualFundsPage />} />
        <Route path="/money/tax-tools" element={<TaxToolsPage />} />
        <Route path="/money/calendar" element={<MoneyCalendarPage />} />
        <Route path="/money/us-tax" element={<UsTaxPage />} />
        <Route path="/money/itr" element={<ItrExportPage />} />
        <Route path="/money/sip-test" element={<SipTestPage />} />
        <Route path="/money/rates" element={<RatesPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/research" element={<ResearchHome />} />
        <Route path="/research/themes" element={<ThemesPage />} />
        <Route path="/research/pulse" element={<PulsePage />} />
        <Route path="/research/compare" element={<ComparePage />} />
        <Route path="/research/watchlist" element={<WatchlistPage />} />
        <Route path="/research/scan" element={<ScanPage />} />
        {/* "Scans" was a row of tabs: its pages are now Find stocks and Market view, so the old address opens the first scan */}
        <Route path="/research/scans" element={<Navigate to="/research/scan" replace />} />
        <Route path="/scans" element={<Navigate to="/research/scan" replace />} />
        <Route path="/watchlist" element={<Navigate to="/research/watchlist" replace />} />
        <Route path="/research/screens" element={<ScreensPage />} />
        <Route path="/research/rotation" element={<RotationPage />} />
        <Route path="/invest/breadth" element={<BreadthPage />} />
        <Route path="/invest/etf-gaps" element={<EtfGapsPage />} />
        <Route path="/invest/holders" element={<HoldersPage />} />
        <Route path="/invest/business-updates" element={<BizUpdatesPage />} />
        <Route path="/invest/stock-lending" element={<StockLendingPage />} />
        <Route path="/invest/margin-funding" element={<MarginFundingPage />} />
        <Route path="/dev/kit" element={import.meta.env.DEV ? <DevKit /> : <AdminOnly what="The design kit"><DevKit /></AdminOnly>} />
        <Route path="/research/filings" element={<FilingsPage />} />
        <Route path="/research/results" element={<ResultsPage />} />
        <Route path="/research/corporate-actions" element={<CorpActionsPage />} />
        <Route path="/research/IN/:symbol/deep" element={<DeepDivePage />} />
        <Route path="/research/US/:symbol/deep" element={<DeepDivePage />} />
        <Route path="/research/investor" element={<InvestorHomePage />} />
        <Route path="/research/:region/:symbol" element={<CompanyPage />} />
        <Route path="*" element={<NotFound signedIn />} />
      </Routes>
      </Suspense>
    </Shell>
  );
}

function App() {
  const nav = useNavigate();
  const goToPlans = useCallback(() => nav("/plans"), [nav]);
  return (
    <AppProvider goToPlans={goToPlans}>
      <Routed />
      <Toast />
    </AppProvider>
  );
}

if (import.meta.env.PROD) registerPwa();
captureRef();          // a friend's invite link: kept until sign-in

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
