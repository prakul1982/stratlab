import { useState } from "react";
import { useApp } from "../lib/app";
import type { Focus, Level } from "../lib/types";
import { Modal } from "./ui";

export const LEVELS: [Level, string, string][] = [
  ["new", "New to this", "Guided start: examples to try, explanations up front, advanced settings folded away."],
  ["some", "I've done a bit", "The standard layout: every tool one tap away, advanced settings folded until you need them."],
  ["pro", "I do this actively", "Every tool in view, including the advanced ones. Detailed settings stay tidy: open them once and they stay open."],
];

export const FOCUSES: [Focus, string, string][] = [
  ["invest", "Investing", "Find good companies and hold them: scans, sector rotation, red flags, deep dives and the management report card."],
  ["trade", "Trading", "Test trading rules on years of real prices, then run them live with fake money: stocks, F&O, options, crypto."],
  ["both", "Both", "Everything side by side."],
];

/** Asked once, after the first sign-in (and once to anyone who answered only the old experience question). Both answers
 * only change what's shown first; every tool stays available, and both can be changed on the Account page. */
export function LevelPrompt({ onDone }: { onDone: () => void }) {
  const { level, focus, setLevel, setFocus } = useApp();
  const [step, setStep] = useState<"focus" | "level">(focus ? "level" : "focus");
  const pickFocus = async (f: Focus) => { await setFocus(f); if (level) onDone(); else setStep("level"); };
  const pickLevel = async (l: Level) => { await setLevel(l); onDone(); };
  if (step === "focus") return (
    <Modal title="What brings you to StratLab?" onClose={() => pickFocus("both")}>
      <p className="muted" style={{ marginBottom: 16 }}>We'll put what you came for first. Everything else stays one tap away, and you can change this any time on the Account page.</p>
      <div className="stack" style={{ gap: 10 }}>
        {FOCUSES.map(([f, title, what]) => (
          <button key={f} className="card explore-card" onClick={() => pickFocus(f)}><b>{title}</b><span className="small muted">{what}</span></button>
        ))}
      </div>
    </Modal>
  );
  return (
    <Modal title={focus === "invest" ? "How much investing have you done?" : "How much trading have you done?"} onClose={() => pickLevel("some")}>
      <p className="muted" style={{ marginBottom: 16 }}>This only changes what starts open. Every tool is available whatever you pick.</p>
      <div className="stack" style={{ gap: 10 }}>
        {LEVELS.map(([l, title, what]) => (
          <button key={l} className="card explore-card" onClick={() => pickLevel(l)}><b>{title}</b><span className="small muted">{what}</span></button>
        ))}
      </div>
    </Modal>
  );
}
