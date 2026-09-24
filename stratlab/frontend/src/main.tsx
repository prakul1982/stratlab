import { StrictMode, useCallback } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
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
import { NotebookPage } from "./pages/NotebookPage";
import { ExperimentPage } from "./pages/ExperimentPage";
import { MarketPage } from "./pages/MarketPage";
import { PaperPage } from "./pages/PaperPage";
import { PlansPage } from "./pages/PlansPage";
import { AccountPage } from "./pages/AccountPage";
import { AdminPage } from "./pages/AdminPage";
import { ComparePage, CompanyPage, PulsePage, ResearchHome, ThemesPage, WatchlistPage } from "./pages/Research";

function Routed() {
  const { session, ready, dataOffline, meError } = useApp();
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
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/new" element={<NewNotebook />} />
        <Route path="/n/:id" element={<NotebookPage />} />
        <Route path="/n/:id/market" element={<MarketPage />} />
        <Route path="/n/:id/e/:v" element={<ExperimentPage />} />
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
