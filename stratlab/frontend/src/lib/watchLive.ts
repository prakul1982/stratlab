/* Live prices for the panel and the charts (MW-1): one client for the whole page. Everything that wants prices says which
 * instruments (`subscribe(...).set(keys)`); the client joins them into one request each 5 seconds for their quotes (the server
 * shares each read for 15 seconds between everyone) and, for the instruments the broker's feed carries, one server-sent-events
 * stream of ticks. If the stream drops it reconnects with a growing pause and the 5-second reads carry on meanwhile. While the
 * page is hidden it stops after two minutes and starts again the moment the page is back. Nothing runs with no subscriber.
 *
 * The transport is a parameter, so the unit tests drive the client with a fake one. */
import type { Tick } from "../charts/price/ticks";
import type { WatchQuote } from "./watch";

export interface LiveHandlers {
  tick?: (key: string, t: Tick) => void;
  quote?: (key: string, q: WatchQuote | null) => void;
  /** The stream's state changed: which keys are on it now. */
  state?: (s: LiveState) => void;
}
export interface LiveState { connected: boolean; streamed: string[]; reason: string | null }
export interface LiveSub { set(keys: string[]): void; close(): void }

export interface Transport {
  /** Open the stream for these keys: the response whose body is the event text. */
  open(keys: string[], signal: AbortSignal): Promise<Response>;
  /** The quotes of up to 24 keys. */
  quotes(keys: string[]): Promise<Record<string, WatchQuote | null>>;
}

export interface LiveOptions {
  pollMs?: number; idleMs?: number; debounceMs?: number; backoffMs?: number[]; closedRetryMs?: number;
  /** Whether the page is showing (default: the document's visibility). */
  visible?: () => boolean;
  now?: () => number;
}

const MAX_KEYS = 40, QUOTE_CHUNK = 24;

/** Events in a stream's text so far: [{event, data}], and what is left over (an event not finished). */
export function parseSse(buf: string): { events: { event: string; data: string }[]; rest: string } {
  const events: { event: string; data: string }[] = [];
  const parts = buf.split("\n\n");
  const rest = parts.pop() ?? "";
  for (const p of parts) {
    let event = "message", data = "";
    for (const line of p.split("\n")) {
      if (line.startsWith(":")) continue;                           // a keep-alive comment
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data += (data ? "\n" : "") + line.slice(5).trim();
    }
    if (data) events.push({ event, data });
  }
  return { events, rest };
}

/** The keys in pieces of at most `n`. */
export function chunks<T>(xs: T[], n: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < xs.length; i += n) out.push(xs.slice(i, i + n));
  return out;
}

/** The markets whose keys are asked of the stream (the ones the broker's feed carries). */
const streamable = (key: string): boolean => /^(IN|MCX|CDS):/.test(key);

export class LiveClient {
  private subs = new Set<{ keys: string[]; h: LiveHandlers }>();
  private ctrl: AbortController | null = null;
  private streamKeys = "";
  private streamed = new Set<string>();
  private connected = false;
  private reason: string | null = null;
  private pollTimer: ReturnType<typeof setTimeout> | undefined;
  private syncTimer: ReturnType<typeof setTimeout> | undefined;
  private retryTimer: ReturnType<typeof setTimeout> | undefined;
  private idleTimer: ReturnType<typeof setTimeout> | undefined;
  private idle = false;
  private failures = 0;
  private gen = 0;
  private polling = false;
  private o: Required<LiveOptions>;
  private t: Transport;

  constructor(t: Transport, o: LiveOptions = {}) {
    this.t = t;
    this.o = {
      pollMs: 5000, idleMs: 120_000, debounceMs: 300, backoffMs: [1000, 2000, 4000, 8000, 16_000, 30_000], closedRetryMs: 60_000,
      visible: () => typeof document === "undefined" || document.visibilityState !== "hidden", now: () => Date.now(), ...o,
    };
    if (typeof document !== "undefined") document.addEventListener("visibilitychange", this.onVisible);
  }

  /** A subscriber: it gets ticks and quotes for the keys it sets. Close it when it goes. */
  subscribe(h: LiveHandlers): LiveSub {
    const sub = { keys: [] as string[], h };
    this.subs.add(sub);
    return {
      set: (keys) => {
        const next = [...new Set(keys)];
        if (next.length === sub.keys.length && next.every((k, i) => k === sub.keys[i])) return;
        sub.keys = next;
        this.changed();
      },
      close: () => { if (this.subs.delete(sub)) this.changed(); },
    };
  }

  /** Every key anyone follows, each once. */
  keys(): string[] {
    return [...new Set([...this.subs].flatMap((s) => s.keys))];
  }

  state(): LiveState { return { connected: this.connected, streamed: [...this.streamed], reason: this.reason }; }

  private emitState() {
    const s = this.state();
    for (const sub of this.subs) sub.h.state?.(s);
  }

  private changed() {
    clearTimeout(this.syncTimer);
    this.syncTimer = setTimeout(() => this.sync(), this.o.debounceMs);
  }

  onVisible = () => {
    if (this.o.visible()) {
      clearTimeout(this.idleTimer);
      if (this.idle) { this.idle = false; this.sync(); }
    } else if (this.subs.size) {
      clearTimeout(this.idleTimer);
      this.idleTimer = setTimeout(() => { this.idle = true; this.stop(); }, this.o.idleMs);
    }
  };

  /** Bring the stream and the reads in line with what is wanted now. */
  private sync() {
    const keys = this.keys();
    if (!keys.length || this.idle) { this.stop(); return; }
    const want = keys.filter(streamable).slice(0, MAX_KEYS).sort().join(",");
    if (want !== this.streamKeys || (!this.ctrl && want && !this.retryTimer)) this.openStream(want);
    if (!want) this.closeStream();
    if (!this.polling) this.poll(true);
  }

  private stop() {
    this.closeStream();
    clearTimeout(this.pollTimer); this.polling = false;
    clearTimeout(this.retryTimer); this.retryTimer = undefined;
  }

  private closeStream() {
    this.gen++;
    this.ctrl?.abort();
    this.ctrl = null; this.streamKeys = ""; this.connected = false;
    if (this.streamed.size) { this.streamed = new Set(); this.emitState(); }
  }

  // ---------- the stream ----------
  private openStream(keys: string) {
    this.closeStream();
    clearTimeout(this.retryTimer); this.retryTimer = undefined;
    if (!keys) return;
    this.streamKeys = keys;
    const gen = this.gen, ctrl = new AbortController();
    this.ctrl = ctrl;
    void this.read(keys.split(","), ctrl, gen);
  }

  private retry(gen: number, after: number) {
    if (gen !== this.gen) return;
    this.connected = false; this.ctrl = null;
    if (this.streamed.size) { this.streamed = new Set(); }
    this.emitState();
    clearTimeout(this.retryTimer);
    const keys = this.streamKeys;
    this.retryTimer = setTimeout(() => { this.retryTimer = undefined; if (gen === this.gen && keys === this.streamKeys) this.openStream(keys); }, after);
  }

  private async read(keys: string[], ctrl: AbortController, gen: number) {
    try {
      const res = await this.t.open(keys, ctrl.signal);
      if (gen !== this.gen) return;
      if (!res.body) throw new Error("no stream");
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      let bye: string | null = null;
      for (;;) {
        const { done, value } = await reader.read();
        if (gen !== this.gen) { void reader.cancel().catch(() => undefined); return; }
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const got = parseSse(buf);
        buf = got.rest;
        for (const ev of got.events) {
          let data: unknown;
          try { data = JSON.parse(ev.data); } catch { continue; }
          if (ev.event === "hello") {
            const h = data as { live?: string[]; reason?: string };
            this.streamed = new Set(h.live ?? []); this.connected = (h.live ?? []).length > 0; this.reason = h.reason ?? null; this.failures = 0;
            this.emitState();
          } else if (ev.event === "tick") this.deliver(data as { k: string; p: number; v: number | null; t: string }[]);
          else if (ev.event === "bye") bye = (data as { reason?: string }).reason ?? "";
        }
      }
      // the stream ended: the server's own goodbye ("reopen" after its age, "poll" when nothing is streamed) or a drop
      if (gen !== this.gen) return;
      if (bye === "poll") this.retry(gen, this.o.closedRetryMs);          // nothing to stream now (the market is shut, the login is off): look again in a minute
      else this.retry(gen, bye === "reopen" ? 0 : this.backoff());
    } catch (e) {
      if (gen !== this.gen || (e as Error)?.name === "AbortError") return;
      this.retry(gen, this.backoff());
    }
  }

  private backoff(): number {
    const b = this.o.backoffMs;
    return b[Math.min(this.failures++, b.length - 1)];
  }

  private deliver(rows: { k: string; p: number; v: number | null; t: string }[]) {
    for (const r of rows) {
      const t = Date.parse(r.t);
      const tick: Tick = { p: r.p, v: r.v ?? null, t: Number.isFinite(t) ? t : this.o.now() };
      for (const s of this.subs) if (s.keys.includes(r.k)) s.h.tick?.(r.k, tick);
    }
  }

  // ---------- the 5-second reads ----------
  private poll(now = false) {
    this.polling = true;
    clearTimeout(this.pollTimer);
    const run = async () => {
      if (!this.keys().length || this.idle) { this.polling = false; return; }
      if (this.o.visible()) await this.readQuotes();
      if (!this.keys().length || this.idle) { this.polling = false; return; }
      this.pollTimer = setTimeout(run, this.o.pollMs);
    };
    if (now) void run(); else this.pollTimer = setTimeout(run, this.o.pollMs);
  }

  private async readQuotes() {
    for (const part of chunks(this.keys(), QUOTE_CHUNK)) {
      let got: Record<string, WatchQuote | null>;
      try { got = await this.t.quotes(part); } catch { continue; }
      for (const k of part) {
        const q = got[k];
        for (const s of this.subs) {
          if (!s.keys.includes(k)) continue;
          s.h.quote?.(k, q ?? null);
          // an instrument the stream doesn't carry moves the chart on its quote's price (delayed or not: the time is the quote's)
          if (q?.price != null && !this.streamed.has(k)) {
            const at = q.at ? Date.parse(q.at) : NaN;
            s.h.tick?.(k, { p: q.price, v: null, t: Number.isFinite(at) ? at : this.o.now() });
          }
        }
      }
    }
  }

  destroy() {
    this.subs.clear();
    this.stop();
    clearTimeout(this.syncTimer); clearTimeout(this.idleTimer);
    if (typeof document !== "undefined") document.removeEventListener("visibilitychange", this.onVisible);
  }
}
