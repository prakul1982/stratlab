import { useRef, type KeyboardEvent, type ReactNode } from "react";

export type Tile = { value: string; title: string; sub?: string; icon?: ReactNode };
export type TileGroup = { title: string; tiles: Tile[] };

/** Icon tiles in titled groups, one choice in all: the friendly replacement for a long dropdown. `icon` is the inside of
 * an 24x24 stroke svg (paths). Arrow keys move through the tiles; a radio group for screen readers. */
export function TilePicker({ label, groups, value, onChange }: { label: string; groups: TileGroup[]; value: string | null; onChange: (v: string) => void }) {
  const root = useRef<HTMLDivElement>(null);
  const flat = groups.flatMap((g) => g.tiles);
  const stop = flat.some((t) => t.value === value) ? value : flat[0]?.value;
  const key = (e: KeyboardEvent) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step || !flat.length) return;
    e.preventDefault();
    const at = Math.max(0, flat.findIndex((t) => t.value === (value ?? stop)));
    const next = flat[(at + step + flat.length) % flat.length];
    onChange(next.value);
    window.requestAnimationFrame(() => root.current?.querySelector<HTMLElement>(`[data-v="${CSS.escape(next.value)}"]`)?.focus());
  };
  return (
    <div ref={root} className="k-tile-groups" role="radiogroup" aria-label={label} onKeyDown={key}>
      {groups.map((g) => (
        <div key={g.title} className="k-tile-group" role="group" aria-label={g.title}>
          <span className="k-eyebrow">{g.title}</span>
          <div className="k-tiles">
            {g.tiles.map((t) => (
              <button key={t.value} type="button" role="radio" className="k-tile" aria-checked={t.value === value} data-v={t.value}
                tabIndex={t.value === stop ? 0 : -1} onClick={() => onChange(t.value)}>
                {t.icon && <span className="ic" aria-hidden="true"><svg viewBox="0 0 24 24">{t.icon}</svg></span>}
                <b>{t.title}</b>
                {t.sub && <span className="sub">{t.sub}</span>}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
