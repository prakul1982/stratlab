import { useState } from "react";

/** How to put StratLab on a phone's home screen, for each browser, and on a laptop a way to get the page onto the phone.
 * Pure (no account code), so the signed-out /app shows it too (DI-029: only Chrome's step was given, none for an iPhone, and
 * a visitor on /app was told to sign in first). */
export function InstallSteps({ ios, phone }: { ios: boolean; phone: boolean }) {
  const [copied, setCopied] = useState(false);
  const url = typeof location !== "undefined" ? `${location.origin}/app` : "/app";
  const copy = async () => {
    try { await navigator.clipboard.writeText(url); setCopied(true); } catch { setCopied(false); }
  };
  const iphone = <li><b>iPhone or iPad (Safari):</b> tap Share <span aria-hidden="true">(the square with an arrow)</span>, then Add to Home Screen, then Add.</li>;
  const android = <li><b>Android (Chrome), or Chrome or Edge on a computer:</b> open the browser menu <span aria-hidden="true">(⋮)</span> and choose Install app, or Add to Home screen.</li>;
  return (
    <div className="k-stack install-steps" data-testid="install-steps">
      <ol className="k-small install-list">{ios ? <>{iphone}{android}</> : <>{android}{iphone}</>}</ol>
      {!phone && (
        <p className="k-small k-muted">On your phone, open <span className="gate-path">{url}</span> and follow the steps above.{" "}
          <button type="button" className="btn quiet sm" onClick={() => void copy()}>{copied ? "Link copied" : "Copy the link"}</button></p>
      )}
    </div>
  );
}

/** A phone or a tablet (a touch screen), not a laptop. */
export const onPhone = () => { try { return matchMedia("(hover: none) and (pointer: coarse)").matches; } catch { return false; } };
