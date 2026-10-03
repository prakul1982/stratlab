"""Realistic requests for every route, the way the app's own pages send them, used as the starting point for the
stress tests (each is then broken in many ways). `{nid}`-style placeholders are filled from the seeded world."""
import base64


def cond(lt, op, rt, lp=None, rp=None, **kw):
    left = {"t": lt, **({"p": lp} if lp else {})}
    right = {"t": rt, **({"p": rp} if rp is not None and rt != "num" else {}), **({"v": rp} if rt == "num" else {})}
    return {"l": left, "op": op, "r": right, **kw}


EMA = {"name": "EMA cross", "tf": "1d", "entry": [cond("ema", "xa", "ema", 10, 30)], "exit": [cond("ema", "xb", "ema", 10, 30)],
       "risk": {"capital": 100000, "riskPct": 2, "sl": 4, "tgt": 0, "brokerage": 20, "slippage": 0.05}}
STRATEGIES = [
    EMA,
    {"name": "ST S2", "tf": "1d", "entry": [cond("stage", "eq", "num", None, 2), cond("price", "gt", "supertrend", None, 10)],
     "exit": [cond("price", "lt", "supertrend", None, 10)], "risk": {"sl": 8, "trail": 5, "sizing": "capital", "perTrade": 50000}},
    {"name": "Intraday RSI", "tf": "5m", "entry": [cond("rsi", "lt", "num", 14, 30)], "exit": [cond("rsi", "gt", "num", 14, 60)],
     "session": {"start": "09:30", "end": "14:45", "squareoff": "15:10", "maxTradesDay": 3, "cooldown": 2, "dailyLossPct": 2},
     "product": "intraday", "risk": {"sl": 1, "tgt": 2, "tgtType": "r", "stopType": "atr", "leverage": 5}},
    {"name": "Both sides", "tf": "1h", "side": "both", "entry": [cond("macd", "xa", "macd_signal")],
     "exit": [cond("macd", "xb", "macd_signal")], "shortEntry": [cond("price", "lt", "bb_lower", None, 20)],
     "shortExit": [cond("price", "gt", "bb_mid", None, 20)], "entryJoin": "any",
     "risk": {"sl": 2, "stopType": "swing", "maxBars": 20}},
    {"name": "Scored", "tf": "15m", "entryJoin": "score", "minScore": 2,
     "entry": [cond("adx", "gt", "num", 14, 25, w=1), cond("stoch_k", "lt", "num", 14, 20, w=1), cond("volume", "gt", "vol_sma", None, 20, w=1)],
     "exit": [cond("price", "lt", "dc_lower", None, 20)], "risk": {"sl": 50, "stopType": "points", "tgt": 100, "tgtType": "points"}},
    {"name": "Candle", "tf": "1d", "entry": [{"l": {"t": "body"}, "op": "gt", "r": {"t": "atr", "k": 1.5}},
                                             {"l": {"t": "price"}, "op": "gt", "r": {"t": "day_high", "ago": 1}}],
     "exit": [{"l": {"t": "price"}, "op": "lt", "r": {"t": "ema", "p": 20, "tf": "1d"}}]},
    {"name": "Empty rules", "tf": "1d", "entry": [], "exit": []},
]
INSTRUMENTS = ["{in_stock}", "CRYPTO:BTC-USD", "US:AAPL", "UK:VOD.L", "FX:USDINR=X", "MCX:GOLDM", "CMDTY:GC=F", "{in_index}"]
OPT = {"name": "Short straddle", "structure": "short_straddle", "exchange": "NFO", "underlying": "NIFTY",
       "legs": [{"side": "sell", "opt": "CE", "offset": 0}, {"side": "sell", "opt": "PE", "offset": 0}],
       "timing": {"entry": "09:30", "lastEntry": "14:00", "squareoff": "15:15"},
       "risk": {"stop": 30, "tgt": 50}}
OPT_SIGNAL = {**OPT, "name": "Signal straddle", "signal": {"rules": {**STRATEGIES[2], "tf": "15m"}, "short": "mirror"}}
GROUP = {"id": "custom", "name": "Mine", "market": "IN", "members": [{"symbol": "RELIANCE"}, {"symbol": "TCS"}, {"symbol": "INFY"}]}
BARS = [{"t": f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}", "o": 100 + i % 9, "h": 104 + i % 9, "l": 97 + i % 9, "c": 101 + i % 7, "v": 10}
        for i in range(320)]


HOLDINGS_CSV = base64.b64encode(b"Symbol,ISIN,Quantity,Average price\nRELIANCE,INE002A01018,10,2500\nTCS,,4,3500\n").decode()


def real_requests(ctx: dict) -> dict:
    """(method, path template) -> list of (query params, JSON body). ctx holds ids from the seeded world."""
    nb_bodies = [{"name": s["name"], "strategy": s, "instrument": inst} for s in STRATEGIES for inst in INSTRUMENTS[:4]]
    return {
        ("POST", "/notebooks"): [({}, b) for b in nb_bodies[:10]] + [({}, {"name": "Group", "strategy": EMA, "group": GROUP})],
        ("PUT", "/notebooks/{nid}"): [({}, {"strategy": s, "notes": "x", "pinned": True}) for s in STRATEGIES]
                                     + [({}, {"instrument": i}) for i in INSTRUMENTS],
        ("POST", "/notebooks/{nid}/experiments"): [({}, {"days": d, "label": "t"}) for d in (5, 30, 365, 3650)]
                                                  + [({}, {"bars": BARS, "upload": {"name": "Mine", "currency": "INR", "step": 1}})],
        ("POST", "/notebooks/{nid}/experiments/{version}/share"): [({}, {}), ({}, {"image": "data:image/png;base64,iVBORw0KGgo="})],
        ("POST", "/notebooks/{nid}/experiments/{version}/library"): [({}, {"description": "Works on trends", "author": "Me"})],
        ("POST", "/library/{eid}/report"): [({}, {"reason": "spam"})],
        ("POST", "/cards/company/{market}/{symbol}"): [({}, {}), ({}, {"image": "data:image/png;base64,iVBORw0KGgo="})],
        ("POST", "/me/referral"): [({}, {"code": ctx.get("code", "x")}), ({}, {})],
        ("GET", "/stocks/{region}/{symbol}"): [({"ref": ctx.get("code", "x")}, None), ({}, None)],
        ("POST", "/live/sessions"): [({}, {"strategy": s, "instrument": i}) for s in STRATEGIES[:4] for i in INSTRUMENTS[:3]],
        ("POST", "/live/groups"): [({}, {"strategy": EMA, "group": GROUP, "fast": {"ticks": True, "maxSpreadPct": 0.5}})],
        ("POST", "/options/preview"): [({}, {"strategy": OPT}), ({}, {"strategy": OPT_SIGNAL}),
                                       ({}, {"strategy": {**OPT, "underlying": "BANKNIFTY", "expiry": "next"}})],
        ("POST", "/options/sessions"): [({}, {"strategy": OPT}), ({}, {"strategy": OPT_SIGNAL})],
        ("GET", "/options/chain"): [({"exchange": "NFO", "underlying": "NIFTY"}, None), ({"exchange": "NFO", "underlying": "BANKNIFTY", "expiry": "next"}, None)],
        ("POST", "/research/scan"): [({}, {"region": r, "set": s}) for r, s in (("IN", "nifty50"), ("IN", "watchlist"), ("US", "us_mega"), ("IN", "banknifty"))],
        ("GET", "/research/rotation"): [({"region": r, "set": s, "interval": i, "tail": 5}, None)
                                        for r, s, i in (("IN", "sectors", "weekly"), ("IN", "size", "daily"), ("US", "sectors", "weekly"), ("IN", "nifty50", "weekly"))],
        ("GET", "/research/search"): [({"q": q, "region": r}, None) for q, r in (("reliance", "IN"), ("apple", "US"), ("hdfc", "IN"))],
        ("GET", "/research/quotes"): [({"region": "IN", "symbols": "RELIANCE,TCS"}, None), ({"region": "US", "symbols": "AAPL"}, None)],
        ("GET", "/research/pulse"): [({"region": "IN"}, None), ({"region": "US", "focus": "tech"}, None)],
        ("GET", "/research/pulse/ai"): [({"region": "IN"}, None)],
        ("GET", "/research/sector"): [({"q": "AI data centers", "region": "US"}, None)],
        ("GET", "/research/compare"): [({"a": "TCS", "b": "INFY", "region": "IN"}, None)],
        ("GET", "/research/company/{region}/{symbol}/ai"): [({}, None)],
        ("PUT", "/research/watchlist"): [({}, {"items": [{"region": "IN", "symbol": "RELIANCE"}, {"region": "US", "symbol": "AAPL"}]})],
        ("GET", "/instruments/search"): [({"q": q, "market": m}, None) for q, m in (("rel", "IN"), ("btc", "CRYPTO"), ("gold", "MCX"), ("aapl", "US"))],
        ("POST", "/ai/strategy"): [({}, {"text": "Buy when RSI crosses above 30 on 15 minute candles, 1% stop"})],
        ("POST", "/import/strategy"): [({}, {"text": "//@version=5\nstrategy('x')\nif ta.crossover(ta.ema(close,9), ta.ema(close,21))\n    strategy.entry('L', strategy.long)", "filename": "x.pine"})],
        ("POST", "/export/strategy"): [({}, {"strategy": s}) for s in STRATEGIES],
        ("POST", "/ask"): [({}, {"q": q}) for q in ("is reliance in stage 2", "deep dive apollo", "backtest ema cross on nifty")],
        ("POST", "/search/ideas"): [({}, {"q": "momentum in midcaps"})],
        ("PUT", "/me/prefs"): [({}, {"level": "new", "focus": "invest"}), ({}, {"focus": "trade"})],
        ("PUT", "/me/alerts"): [({}, {"alerts_enabled": True, "telegram_chat_id": "12345", "alert_email": "a@b.co", "daily_report": True})],
        ("POST", "/push/subscribe"): [({}, {"subscription": {"endpoint": "https://push.example.com/x", "keys": {"p256dh": "k", "auth": "a"}}})],
        ("POST", "/push/unsubscribe"): [({}, {"subscription": {"endpoint": "https://push.example.com/x", "keys": {"p256dh": "k", "auth": "a"}}})],
        ("POST", "/billing/subscribe"): [({}, {"plan": "pro", "period": "month"})],
        ("POST", "/billing/verify"): [({}, {"razorpay_payment_id": "pay_1", "razorpay_subscription_id": "sub_1", "razorpay_signature": "x"})],
        ("POST", "/admin/users/{user_id}/plan"): [({}, {"plan": "basic", "days": 30}), ({}, {"plan": "free"})],
        ("POST", "/admin/promo"): [({}, {"days": 5})],
        ("POST", "/admin/audit"): [({}, {"set": "nifty50"}), ({}, {"symbols": ["RELIANCE", "TCS"], "docs": True})],
        ("POST", "/admin/library/{eid}"): [({}, {"action": "hide"}), ({}, {"action": "restore"})],
        ("POST", "/research/deep/{symbol}/read"): [({}, None), ({"refresh": "true"}, None)],
        ("POST", "/research/deep/{symbol}/card"): [({}, None)],
        ("PUT", "/research/scan/alerts"): [({}, {"on": True})],
        ("PUT", "/research/filings/alerts"): [({}, {"on": True})],
        ("POST", "/holdings/import"): [({}, {"filename": "holdings.csv", "data": HOLDINGS_CSV}),
                                       ({}, {"filename": "holdings.csv", "data": HOLDINGS_CSV, "mode": "add"})],
        ("PUT", "/holdings"): [({}, {"items": [{"symbol": "RELIANCE", "qty": 10, "avg": 2500}, {"symbol": "543210", "qty": 5}]})],
    }
