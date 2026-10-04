"""Admin → Check every feature: each part of StratLab run once on the live server, on live data, with what came back
compared to what it should be. The companies audit covers the deep dive; this covers everything else: prices in
every market (and how fresh they are), a backtest per market, the scans, sector rotation, the option chain, filings,
company pages, news, the database and the holiday calendar. No AI is used."""
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .data import calendar
from .data.markets import BY_ID

TIMEOUT = 45          # seconds a single check may take before it counts as failed


def _result(name: str, area: str, state: str, detail: str, seconds: float | None = None) -> dict:
    return {"name": name, "area": area, "state": state, "detail": detail, "seconds": seconds}


def last_session(market: str, today: date) -> date:
    """The most recent trading day before today: its daily candle must exist by now."""
    d = today - timedelta(days=1)
    for _ in range(10):
        if calendar.is_trading_day(market, d):
            return d
        d -= timedelta(days=1)
    return d


def market_today(market: str) -> date:
    """Today where the market trades: in India after midnight, New York's session may still be running."""
    return datetime.now(ZoneInfo((BY_ID.get(market) or {}).get("tz") or "UTC")).date()


def check_market(registry, market: str, today: date | None = None) -> dict:
    """Daily prices for the market's first ready-made instrument: present, sane, and no older than the last session
    (by the market's own date unless `today` is given)."""
    today = today or market_today(market)
    prov = registry.provider(market)
    if prov is None:
        return _result(f"Prices: {market}", "Prices", "fail", "Market not connected.")
    if not prov.ready():
        return _result(f"Prices: {market}", "Prices", "warn", "Offline right now (for India: the day's broker login isn't done).")
    inst = (prov.defaults() or [None])[0]
    if not inst:
        return _result(f"Prices: {market}", "Prices", "fail", "No default instrument to check.")
    bars = prov.history(inst, "1d", 30)
    if not bars:
        return _result(f"Prices: {market}", "Prices", "fail", f"No daily prices for {inst['symbol']}.")
    bad = [b for b in bars if not (0 < b["l"] <= min(b["o"], b["c"]) and max(b["o"], b["c"]) <= b["h"])]
    last = datetime.fromisoformat(bars[-1]["t"]).date()
    expected = last_session(market, today)
    if bad:
        return _result(f"Prices: {market}", "Prices", "fail", f"{len(bad)} candles of {inst['symbol']} have high/low outside open/close.")
    if last < expected:
        return _result(f"Prices: {market}", "Prices", "fail",
                       f"{inst['symbol']}: last daily candle {last}, but {expected} was a trading day." + _why_stale(prov, inst))
    return _result(f"Prices: {market}", "Prices", "pass", f"{inst['symbol']}: {len(bars)} daily candles, latest {last}, close {bars[-1]['c']:,.2f}.")


def _why_stale(prov, inst) -> str:
    """For the global market data source: what the source itself says, to tell a late source from a StratLab bug.
    Its own last quote time, the latest candle in a fresh short download, and days it sent with blank prices."""
    y = getattr(prov, "yahoo", None)
    if y is None:
        return ""
    try:
        from datetime import datetime as dt, timezone as tz
        raw = y._raw_chart(inst["token"], "1d", 7)
        res = ((raw or {}).get("chart") or {}).get("result") or [{}]
        meta, ts = res[0].get("meta") or {}, res[0].get("timestamp") or []
        q = (((res[0].get("indicators") or {}).get("quote")) or [{}])[0]
        closes = q.get("close") or []
        days = [dt.fromtimestamp(t, tz.utc).date().isoformat() for t in ts]
        blank = [d for d, c in zip(days, closes) if c is None]
        quote_at = dt.fromtimestamp(meta["regularMarketTime"], tz.utc).strftime("%Y-%m-%d %H:%M UTC") if meta.get("regularMarketTime") else "?"
        return (f" The source's last quote is from {quote_at}; a fresh download's latest day is {days[-1] if days else 'none'}"
                + (f"; it sent {', '.join(blank)} with blank prices, which are left out" if blank else "") + ".")
    except Exception as e:
        return f" (Couldn't ask the source why: {str(e)[:80]}.)"


def check_backtest(registry, market: str) -> dict:
    from . import research
    from .models import Strategy
    from .universes import _Req
    prov = registry.provider(market)
    if prov is None or not prov.ready():
        return _result(f"Backtest: {market}", "Backtests", "warn", "Market offline, skipped.")
    inst = (prov.defaults() or [None])[0]
    s = Strategy(name="Check", tf="1d", entry=[{"l": {"t": "ema", "p": 10}, "op": "xa", "r": {"t": "ema", "p": 30}}],
                 exit=[{"l": {"t": "ema", "p": 10}, "op": "xb", "r": {"t": "ema", "p": 30}}])
    out = research.run(s, research.load(registry, s, _Req(inst["id"], 730)))
    st, v = out.get("stats") or {}, out.get("verdict") or {}
    costs = out.get("costs") or {}
    if not v.get("verdict"):
        return _result(f"Backtest: {market}", "Backtests", "fail", f"{inst['symbol']}: no verdict came back.")
    if st.get("n", 0) > 0 and not costs.get("items"):
        return _result(f"Backtest: {market}", "Backtests", "fail", f"{inst['symbol']}: {st['n']} trades but no costs charged.")
    return _result(f"Backtest: {market}", "Backtests", "pass",
                   f"{inst['symbol']}, 2 years: {st.get('n', 0)} trades, verdict \"{v['verdict']}\", costs charged.")


def check_scan(registry, market: str, set_id: str) -> dict:
    from . import scan, universes
    preset = next(p for p in universes.PRESETS[market] if p["id"] == set_id)
    out = scan.run(registry, market, [{"symbol": s} for s in preset["symbols"]])
    rows, missing = out.get("rows") or [], out.get("missing") or []
    share = len(rows) / max(1, len(preset["symbols"]))
    state = "pass" if share >= 0.95 else "warn" if share >= 0.8 else "fail"
    extra = f"; missing {', '.join(missing[:6])}" if missing else ""
    return _result(f"Scan: {preset['name']}", "Scans", state, f"{len(rows)} of {len(preset['symbols'])} stocks scanned{extra}.")


def check_rotation(registry, market: str) -> dict:
    from . import rotation
    out = rotation.run(registry, market, "sectors", None, "weekly", 5)
    rows, skipped = out.get("rows") or [], out.get("skipped") or []
    total = len(rows) + len(skipped)
    state = "pass" if rows and len(rows) >= 0.8 * total else "warn" if rows else "fail"
    return _result(f"Sector rotation: {market}", "Rotation", state,
                   f"{len(rows)} of {total} sectors placed against {out.get('benchmark')}" + (f"; skipped {', '.join(skipped[:4])}" if skipped else "") + ".")


def check_options(options, today: date) -> dict:
    if not options.ready():
        return _result("Option chain: NIFTY", "Options", "warn", "Offline right now (the day's broker login isn't done).")
    c = options.chain("NFO", "NIFTY", "current", 10)
    rows, expiry = c.get("rows") or [], c.get("expiry")
    if not rows or not expiry:
        return _result("Option chain: NIFTY", "Options", "fail", "No strikes came back.")
    if expiry < today.isoformat():
        return _result("Option chain: NIFTY", "Options", "fail", f"Offered expiry {expiry}, which has passed.")
    if not calendar.is_trading_day("IN", date.fromisoformat(expiry)):
        return _result("Option chain: NIFTY", "Options", "fail", f"Expiry {expiry} falls on a closed day.")
    quoted = sum(1 for r in rows for side in ("ce", "pe") if (r.get(side) or {}).get("ltp"))
    two_sided = sum(1 for r in rows for side in ("ce", "pe") if (r.get(side) or {}).get("bid") and (r.get(side) or {}).get("ask"))
    state = "pass" if quoted >= len(rows) else "warn"
    return _result("Option chain: NIFTY", "Options", state,
                   f"Expiry {expiry}, spot {c.get('spot')}, {len(rows)} strikes; {quoted} prices, {two_sided} with bid and ask.")


def check_filings(feed) -> dict:
    items = feed.announcements("RELIANCE")
    if not items:
        return _result("Exchange filings", "Filings", "warn", "Reliance has no filings in the window, which is unusual.")
    newest = items[0]["at"][:10]
    return _result("Exchange filings", "Filings", "pass", f"{len(items)} Reliance filings; newest {newest}.")


def check_insider_trades(feed) -> dict:
    """The exchange's insider-trading disclosures (one call), which the deals table, the checklist, the screens and the
    deal alerts read. A big company with none in a year would mean the feed changed shape."""
    items = feed.insider_trades("RELIANCE")
    if not items:
        return _result("Insider trades", "Filings", "warn", "Reliance has no insider-trading disclosures in the last year, which is unusual.")
    return _result("Insider trades", "Filings", "pass", f"{len(items)} Reliance insider-trading disclosures; newest {items[0]['date']}.")


def check_surveillance(feed) -> dict:
    """The exchange's surveillance lists (ASM, GSM, ESM, the F&O ban file and the price-band file), which the badges,
    the screens' filter and the surveillance alerts read. These addresses can't be tried from a test machine, so this
    is where a changed address or shape shows first. Each list is read on its own; any that fails is named."""
    got, bad = [], []
    for name, fn, count in (("ASM", feed.asm_list, lambda x: len(x.get("lt") or {}) + len(x.get("st") or {})),
                            ("GSM", feed.gsm_list, len), ("ESM", feed.esm_list, len),
                            ("F&O ban", feed.fo_ban, lambda x: len(x[1])), ("price bands", feed.security_bands, len)):
        try:
            got.append(f"{name} {count(fn())}")
        except Exception as e:
            bad.append(f"{name}: {str(e)[:100]}")
    if not got:
        return _result("Surveillance lists", "Filings", "fail", "No list answered. " + " · ".join(bad))
    detail = "Read: " + ", ".join(got) + "." + (" Failed: " + " · ".join(bad) if bad else "")
    return _result("Surveillance lists", "Filings", "warn" if bad else "pass", detail)


BSE_REFUSING = ("BSE is turning this server's requests away: {why}. Only companies listed on BSE alone are affected: "
                "companies on both exchanges read their filings from NSE, and the BSE-only ones show their documents as "
                "not checked yet and are tried again in small batches every hour until BSE answers.")


def check_bse_filings(bse) -> dict:
    """BSE's feed, which serves the companies listed only on BSE; Reliance (500325) files on both exchanges. BSE
    refusing this server is a warning, not a failure: every company on NSE too reads NSE's filings, and the BSE-only
    ones wait and are retried."""
    from .intel.net import SourceError
    try:
        items = bse.announcements("500325")
    except SourceError as e:
        if not e.busy:
            raise
        why = str(e).split(" Try again")[0].rstrip(".")
        return _result("BSE filings", "Filings", "warn", BSE_REFUSING.format(why=why[:1].lower() + why[1:]))
    if not items:
        return _result("BSE filings", "Filings", "warn", "Reliance has no BSE filings in the window, which is unusual.")
    pdfs = sum(1 for i in items if i.get("url"))
    return _result("BSE filings", "Filings", "pass" if pdfs else "warn",
                   f"{len(items)} Reliance filings on BSE, {pdfs} with a document; newest {items[0]['at'][:10]}.")


def check_company(hub, region: str, symbol: str) -> dict:
    c = hub.company(region, symbol)
    down = [s["source"] for s in c.get("sources", []) if not s.get("ok")]
    price = (c.get("quote") or {}).get("price")
    state = "pass" if price and not down else "warn" if price else "fail"
    return _result(f"Company page: {symbol}", "Research", state,
                   f"Price {price}" + (f"; sources not answering: {', '.join(down)}" if down else "; every source answered") + ".")


def check_news(hub) -> dict:
    items = hub.headlines("IN")
    return _result("News", "Research", "pass" if items else "warn", f"{len(items)} market headlines.")


def check_database(db) -> dict:
    key = "check:roundtrip"
    stamp = datetime.now(timezone.utc).isoformat()
    db.set_setting(key, stamp)
    back = db.get_setting(key)
    return _result("Database", "Server", "pass" if back == stamp else "fail",
                   "Saved and read back a value." if back == stamp else "A saved value didn't read back the same.")


def check_calendar(today: date) -> dict:
    """Every market with exchange holidays: a warning if any has fewer than 60 days of them known ahead."""
    rows = [r for r in calendar.all_coverage(today) if r["state"] != "none"]
    short = [r for r in rows if r["state"] != "ok"]
    india = next((r for r in rows if r["market"] == "IN"), None)
    if short:
        detail = "Fewer than 60 days of holidays known: " + ", ".join(
            f"{r['name']} ({r['days_left']} days)" if r["days_left"] is not None else f"{r['name']} (none loaded)" for r in short) + "."
    else:
        detail = (f"Holidays known at least 60 days ahead in all {len(rows)} markets"
                  + (f"; India's until {india['known_until']} ({india['days_left']} days)." if india and india["known_until"] else "."))
    return _result("Holiday calendar", "Server", "warn" if short else "pass", detail)


def check_rules(today: date, watch: dict | None = None) -> dict:
    """Rates and rules last reviewed: a warning when an area of rules.py is more than 90 days old, a known change day
    (1 April, the quarterly small-savings rates, the SEC's fiscal year) has passed since its review, or the daily
    rules watch found a change nobody has marked seen."""
    from . import rules
    return rules.check(today, watch=watch)


def run_all(checks: list[tuple[str, callable]]) -> dict:
    """Run every check in parallel, each with a time limit; a check that raises or runs out of time is a failure,
    never the end of the run."""
    out = []
    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="check") as pool:
        futures = [(name, area, pool.submit(_timed, fn)) for name, area, fn in checks]
        for name, area, f in futures:
            try:
                res, secs = f.result(timeout=TIMEOUT)
                res["seconds"] = secs
                out.append(res)
            except FutureTimeout:
                out.append(_result(name, area, "fail", f"Took longer than {TIMEOUT} seconds."))
            except Exception as e:
                msg = getattr(e, "detail", None)
                msg = msg.get("message") if isinstance(msg, dict) else (str(e) or e.__class__.__name__)
                out.append(_result(name, area, "fail", str(msg)[:240]))
    counts = {k: sum(1 for r in out if r["state"] == k) for k in ("pass", "warn", "fail")}
    return {"at": datetime.now(timezone.utc).isoformat(), "counts": counts, "checks": out}


def _timed(fn):
    t = time.monotonic()
    res = fn()
    return res, round(time.monotonic() - t, 1)
