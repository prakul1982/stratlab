import { lazy, StrictMode, Suspense, useCallback, useState, type ComponentType } from "react";
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
import { AppProvider, useApp } from "./lib/app";
import { registerPwa } from "./lib/pwa";
import { Shell } from "./components/Shell";
import { Loading, Toast } from "./components/ui";
import { Login } from "./pages/Login";
import { LEGAL_PAGES, LegalPage } from "./pages/LegalPage";
import { Home, NewNotebook, NotebooksHome } from "./pages/Home";

// every page but the first ones loads when it's opened, so the app starts fast
const page = <K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) =>
  lazy(() => load().then((m) => ({ default: m[name] })));
const NotebookPage = page(() => import("./pages/NotebookPage"), "NotebookPage");
const ExperimentPage = page(() => import("./pages/ExperimentPage"), "ExperimentPage");
const MarketPage = page(() => import("./pages/MarketPage"), "MarketPage");
const OptionsPage = page(() => import("./pages/OptionsPage"), "OptionsPage");
const ImportPage = page(() => import("./pages/ImportPage"), "ImportPage");
const PublicVerdict = page(() => import("./pages/PublicVerdict"), "PublicVerdict");
const OptionsSession = page(() => import("./pages/OptionsSession"), "OptionsSession");
const PaperPage = page(() => import("./pages/PaperPage"), "PaperPage");
const PlansPage = page(() => import("./pages/PlansPage"), "PlansPage");
const AccountPage = page(() => import("./pages/AccountPage"), "AccountPage");
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
const DeepDivePage = page(() => import("./pages/DeepDive"), "DeepDivePage");
const InvestorHomePage = page(() => import("./pages/InvestorHome"), "InvestorHomePage");
const RotationPage = page(research, "RotationPage");
const FilingsPage = page(research, "FilingsPage");
const CompanyPage = page(research, "CompanyPage");

/** Indian data is offline: say why in plain words. On a weekend or holiday that's expected, not a fault. */
function DataBanner({ note }: { note: { closed: "weekend" | "holiday" | null; back_at: string | null } | null }) {
  const back = note?.back_at ? new Date(note.back_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : null;
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
      <Link to="/account" className="btn sm quiet">Run a connection check</Link>
    </div>
  );
}

/** The launch offer: every Pro feature free for everyone until a date. Dismissed per offer. */
function PromoBanner({ until }: { until: string }) {
  const key = `stratlab.promo.seen.${until.slice(0, 10)}`;
  const [hidden, setHidden] = useState(() => { try { return localStorage.getItem(key) === "1"; } catch { return false; } });
  if (hidden) return null;
  const day = new Date(until).toLocaleDateString(undefined, { day: "numeric", month: "long" });
  return (
    <div className="banner promo-banner">
      <span><b>Launch offer:</b> every Pro feature is free for everyone until {day}. After that, your plan's limits apply again.</span>
      <button className="btn sm quiet" onClick={() => { try { localStorage.setItem(key, "1"); } catch { /* storage off */ } setHidden(true); }}>Got it</button>
    </div>
  );
}

function Routed() {
  const { session, ready, dataOffline, meError, me } = useApp();
  const loc = useLocation();
  // shared verdicts are public: no sign-in needed
  if (LEGAL_PAGES.some((p) => p.path === loc.pathname)) return <LegalPage />;   // policies are public: no sign-in needed
  if (loc.pathname.startsWith("/verdict/")) return <Suspense fallback={<Loading label="Opening the verdict" />}><Routes><Route path="/verdict/:token" element={<PublicVerdict />} /></Routes></Suspense>;
  if (!ready) return <Loading label="Opening StratLab" />;
  if (!session) return <Login />;
  return (
    <Shell>
      {meError && <div className="banner" role="alert">StratLab couldn't load your account: {meError}</div>}
      {dataOffline && !meError && <DataBanner note={me?.data_note ?? null} />}
      {me?.promo && <PromoBanner until={me.promo.until} />}
      <Suspense fallback={<Loading label="Opening" />}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/notebooks" element={<NotebooksHome />} />
        <Route path="/new" element={<NewNotebook />} />
        <Route path="/n/:id" element={<NotebookPage />} />
        <Route path="/n/:id/market" element={<MarketPage />} />
        <Route path="/n/:id/compare" element={<CompareExperiments />} />
        <Route path="/n/:id/e/:v" element={<ExperimentPage />} />
        <Route path="/import" element={<ImportPage />} />
        <Route path="/library" element={<LibraryPage />} />
        <Route path="/options" element={<OptionsPage />} />
        <Route path="/options/s/:sid" element={<OptionsSession />} />
        <Route path="/paper" element={<PaperPage />} />
        <Route path="/paper/:sid" element={<PaperPage />} />
        <Route path="/plans" element={<PlansPage />} />
        <Route path="/account" element={<AccountPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/research" element={<ResearchHome />} />
        <Route path="/research/themes" element={<ThemesPage />} />
        <Route path="/research/pulse" element={<PulsePage />} />
        <Route path="/research/compare" element={<ComparePage />} />
        <Route path="/research/watchlist" element={<WatchlistPage />} />
        <Route path="/research/scan" element={<ScanPage />} />
        <Route path="/research/rotation" element={<RotationPage />} />
        <Route path="/research/filings" element={<FilingsPage />} />
        <Route path="/research/IN/:symbol/deep" element={<DeepDivePage />} />
        <Route path="/research/investor" element={<InvestorHomePage />} />
        <Route path="/research/:region/:symbol" element={<CompanyPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
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

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
