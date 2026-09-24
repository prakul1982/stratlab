import { useEffect, useState } from "react";
import { supabase } from "../lib/api";
import { Google } from "../components/Icons";
import { Logo } from "../components/Logo";

export function Login() {
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const p = new URLSearchParams(location.search + "&" + location.hash.replace(/^#/, ""));
    const d = p.get("error_description");
    if (!d) return;
    setError(/exchange external code/i.test(d)
      ? "Google sign-in couldn't finish: the Google Client ID or Secret saved in Supabase doesn't match your Google Cloud OAuth client."
      : `Sign-in failed: ${d}`);
    history.replaceState(null, "", location.pathname);
  }, []);

  const signIn = () => supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: location.origin + "/" } });

  return (
    <div className="ruled" style={{ minHeight: "100vh", display: "grid", gridTemplateColumns: "minmax(0, 1.1fr) minmax(0, 1fr)" }}>
      <div style={{ padding: "48px clamp(20px, 6vw, 88px)", display: "flex", flexDirection: "column", justifyContent: "center", gap: 22 }}>
        <div className="brand" role="img" aria-label="StratLab"><Logo size={70} /></div>
        <h1 className="serif" style={{ fontSize: "clamp(40px, 5.4vw, 68px)", lineHeight: 1.02, fontWeight: 400, letterSpacing: "-0.03em", maxWidth: "13ch" }}>
          Is your trading idea real, or just <em>lucky</em>?
        </h1>
        <p className="serif" style={{ fontSize: 21, lineHeight: 1.45, color: "var(--ink-2)", maxWidth: "36ch" }}>
          Write a strategy in plain words. StratLab tests it on years of real prices, runs four honesty checks, and tells you straight.
        </p>
        <button className="btn outline" style={{ alignSelf: "flex-start", minHeight: 52, padding: "0 22px", fontSize: 16, background: "var(--card)" }} onClick={signIn}>
          <Google />Continue with Google
        </button>
        {error && <p className="banner" role="alert">{error}</p>}
        <p className="small muted" style={{ maxWidth: "48ch" }}>
          Indian stocks and F&amp;O, crypto, or your own data. Paper trading only: no real orders are placed, and nothing here is investment advice.
        </p>
      </div>
      <div className="login-art" style={{ padding: 32, display: "flex", alignItems: "center", justifyContent: "center", borderLeft: "1px solid var(--line)", background: "var(--paper-2)" }}>
        <div className="card stack" style={{ maxWidth: 440, width: "100%", gap: 14, boxShadow: "var(--shadow)" }} aria-label="Example verdict">
          <span className="eyebrow">Experiment v3 · NIFTY 50 · 38 trades</span>
          <span className="serif" style={{ fontSize: 58, lineHeight: 0.95, letterSpacing: "-0.03em", color: "var(--orange)" }}>Probably luck.</span>
          <p className="serif" style={{ fontSize: 17, color: "var(--ink-2)" }}>It made money on the years it was tuned on, then lost on years it had never seen.</p>
          <div className="stack small" style={{ gap: 8, borderTop: "1px solid var(--line)", paddingTop: 14 }}>
            {[["Unseen data", "fail"], ["Nearby settings", "fail"], ["Bad-luck drawdown", "warn"], ["Enough trades", "pass"]].map(([t, s]) => (
              <div key={t} className="spread"><span>{t}</span><span className={`badge ${s}`}>{s === "pass" ? "Passed" : s === "fail" ? "Failed" : "Warning"}</span></div>
            ))}
          </div>
          <span className="small muted">Sample result</span>
        </div>
      </div>
      <style>{`@media (max-width: 860px){ .login-art{ display:none !important } div.ruled{ grid-template-columns: 1fr !important } }`}</style>
    </div>
  );
}
