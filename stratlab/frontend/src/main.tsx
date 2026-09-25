import { lazy, StrictMode, Suspense, useCallback, type ComponentType } from "react";
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
import { Shell } from "./components/Shell";
import { Loading, Toast } from "./components/ui";
import { Login } from "./pages/Login";
import { Home, NewNotebook } from "./pages/Home";

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
const CompanyPage = page(research, "CompanyPage");

function Routed() {
  const { session, ready, dataOffline, meError } = useApp();
  const loc = useLocation();
  // shared verdicts are public: no sign-in needed
  if (loc.pathname.startsWith("/verdict/")) return <Suspense fallback={<Loading label="Opening the verdict" />}><Routes><Route path="/verdict/:token" element={<PublicVerdict />} /></Routes></Suspense>;
  if (!ready) return <Loading label="Opening StratLab" />;
  if (!session) return <Login />;
  return (
    <Shell>
      {meError && <div className="banner" role="alert">StratLab couldn't load your account: {meError}</div>}
      {dataOffline && !meError && (
        <div className="banner">
          <span>Indian market data is offline until today's data login completes. Crypto and your own data still work.</span>
          <Link to="/account" className="btn sm quiet">Run a connection check</Link>
        </div>
      )}
      <Suspense fallback={<Loading label="Opening" />}>
      <Routes>
        <Route path="/" element={<Home />} />
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

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
