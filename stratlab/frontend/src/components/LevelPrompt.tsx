import { useApp } from "../lib/app";
import type { Level } from "../lib/types";
import { Modal } from "./ui";

export const LEVELS: [Level, string, string][] = [
  ["new", "New to trading", "Guided start: classic ideas to test, explanations up front, advanced settings folded away."],
  ["some", "I've traded a bit", "The standard layout: every tool one tap away, advanced settings folded until you need them."],
  ["pro", "I trade actively", "Every tool in view, including the advanced ones. Detailed settings stay tidy: open them once and they stay open."],
];

/** Asked once, after the first sign-in. It only changes defaults; every tool stays available either way. */
export function LevelPrompt({ onDone }: { onDone: (l: Level) => void }) {
  const { setLevel } = useApp();
  const pick = async (l: Level) => { await setLevel(l); onDone(l); };
  return (
    <Modal title="How much trading have you done?" onClose={() => pick("some")}>
      <p className="muted" style={{ marginBottom: 16 }}>This only changes what starts open. Every tool is available whatever you pick, and you can change it any time on the Account page.</p>
      <div className="stack" style={{ gap: 10 }}>
        {LEVELS.map(([l, title, what]) => (
          <button key={l} className="card explore-card" onClick={() => pick(l)}><b>{title}</b><span className="small muted">{what}</span></button>
        ))}
      </div>
    </Modal>
  );
}
