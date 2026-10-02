from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

RefType = Literal[
    "price", "num", "sma", "ema", "rsi",
    "macd", "macd_signal", "macd_hist",
    "bb_upper", "bb_mid", "bb_lower",
    "vwap", "supertrend", "stage",
    "adx", "stoch_k", "atr_pct", "dc_upper", "dc_lower", "volume", "vol_sma",
    # the candle itself, and the trading day it belongs to
    "open", "high", "low", "body", "upper_wick", "lower_wick", "range", "atr",
    "prev_close", "day_open", "day_high", "day_low", "day_chg",
]
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class Ref(BaseModel):
    t: RefType
    p: Optional[float] = Field(None, ge=1, le=500)   # period (MACD: fast length)
    m: Optional[float] = Field(None, gt=0, le=500)   # MACD slow length, BB std-devs, Supertrend multiplier
    v: Optional[float] = None                         # value when t == "num"
    ago: Optional[int] = Field(None, ge=0, le=100)   # the value this many candles ago (0 or empty = this candle)
    k: Optional[float] = Field(None, gt=0, le=100)   # multiply the value, e.g. 1.5 x candle body
    tf: Optional[Literal["15m", "1h", "1d"]] = None   # compute on a higher timeframe (completed candles only)

    @model_validator(mode="after")
    def _num_needs_value(self):
        if self.t == "num" and self.v is None:
            raise ValueError("A number in a rule needs a value.")
        return self


class Cond(BaseModel):
    l: Ref
    op: Literal["xa", "xb", "gt", "lt", "eq"]   # eq: "is", for whole-number values such as Stage
    r: Ref
    w: Optional[float] = Field(None, gt=0, le=10)    # weight when entry rules are scored


class Risk(BaseModel):
    capital: float = Field(500000, gt=0, le=1e10)
    riskPct: float = Field(1, gt=0, le=100)
    maxAlloc: float = Field(100, gt=0, le=100)
    sl: float = Field(2, ge=0, le=100000)
    tgt: float = Field(0, ge=0, le=100000)
    brokerage: float = Field(20, ge=0, le=1e6)
    slippage: float = Field(0.05, ge=0, le=5)
    trail: float = Field(0, ge=0, lt=100)       # trailing stop, % below the best price since entry (0 = off)
    maxBars: int = Field(0, ge=0, le=5000)      # close the trade after this many candles (0 = off)
    # what `sl` means: % of price, price points, a multiple of ATR(14), or the swing low/high of the last N candles
    stopType: Literal["pct", "points", "atr", "swing"] = "pct"
    # what `tgt` means: % of price, price points, or a multiple of the stop distance (R)
    tgtType: Literal["pct", "points", "r"] = "pct"
    # size by risk (riskPct of capital lost at the stop) or a fixed capital per trade, times leverage
    sizing: Literal["risk", "capital"] = "risk"
    perTrade: float = Field(0, ge=0, le=1e10)   # capital per trade when sizing == "capital" (0 = maxAlloc % of capital)
    leverage: float = Field(1, ge=1, le=20)

    @model_validator(mode="after")
    def _units(self):
        if self.stopType == "pct" and self.sl >= 100:
            raise ValueError("A stop loss in percent must be under 100%.")
        return self


class Session(BaseModel):
    """Intraday rules. Times are the exchange's local time and refer to when a candle closes."""
    start: str = Field("", pattern=r"^$|" + HHMM)        # no new trades before this time
    end: str = Field("", pattern=r"^$|" + HHMM)          # no new trades after this time
    squareoff: str = Field("", pattern=r"^$|" + HHMM)    # close any open trade at this time
    maxTradesDay: int = Field(0, ge=0, le=100)           # 0 = no limit
    cooldown: int = Field(0, ge=0, le=500)               # candles to wait after a trade closes
    dailyLossPct: float = Field(0, ge=0, le=100)         # stop for the day after losing this % of capital


class Strategy(BaseModel):
    name: str = Field("Untitled strategy", max_length=80)
    tf: Literal["1d", "1h", "15m", "5m"] = "1d"
    text: str = Field("", max_length=4000)
    entry: list[Cond] = Field(default_factory=list, max_length=12)
    exit: list[Cond] = Field(default_factory=list, max_length=12)
    entryJoin: Literal["all", "any", "score"] = "all"
    minScore: float = Field(0, ge=0, le=120)             # with entryJoin == "score" (0 = every rule)
    side: Literal["long", "short", "both"] = "long"      # both: `entry`/`exit` go long, `shortEntry`/`shortExit` go short
    shortEntry: list[Cond] = Field(default_factory=list, max_length=12)
    shortExit: list[Cond] = Field(default_factory=list, max_length=12)
    session: Session = Field(default_factory=Session)
    product: Literal["auto", "delivery", "intraday"] = "auto"   # India cash: intraday (MIS) costs; auto = intraday when squaring off
    risk: Risk = Field(default_factory=Risk)

    def all_conds(self) -> list[Cond]:
        return [*self.entry, *self.exit, *self.shortEntry, *self.shortExit]


class Bar(BaseModel):
    t: str = Field(..., max_length=40)
    o: float
    h: float
    l: float
    c: float
    v: float = 0


class UploadMeta(BaseModel):
    name: str = Field("Uploaded data", max_length=60)
    currency: str = Field("", max_length=8)
    step: float = Field(1, gt=0, le=1e6)       # smallest quantity you can trade: 1 share, 0.0001 BTC


class DataReq(BaseModel):
    """Where the candles come from: a market instrument, or uploaded bars."""
    instrument: Optional[str] = Field(None, max_length=60)      # "IN:256265", "CRYPTO:BTC-USD"
    instrument_token: Optional[int] = None                      # older clients: a Kite token
    days: int = Field(365, ge=5, le=3650)
    bars: Optional[list[Bar]] = Field(None, max_length=50000)
    upload: Optional[UploadMeta] = None

    @model_validator(mode="after")
    def _source(self):
        if self.instrument is None and self.instrument_token is not None:
            self.instrument = f"IN:{self.instrument_token}"
        return self


class LiveStartReq(BaseModel):
    strategy: Strategy
    instrument: Optional[str] = Field(None, max_length=60)
    instrument_token: Optional[int] = None

    @model_validator(mode="after")
    def _source(self):
        if self.instrument is None and self.instrument_token is not None:
            self.instrument = f"IN:{self.instrument_token}"
        if self.instrument is None:
            raise ValueError("Pick an instrument.")
        return self


class GroupMember(BaseModel):
    id: Optional[str] = Field(None, max_length=60)
    symbol: str = Field(..., min_length=1, max_length=40)


class GroupReq(BaseModel):
    """Test on a group of instruments together (one market) instead of one."""
    id: str = Field("custom", max_length=40)
    name: str = Field("My group", min_length=1, max_length=60)
    market: str = Field(..., max_length=10)
    members: list[GroupMember] = Field(..., min_length=2, max_length=50)
    maxOpen: int = Field(10, ge=1, le=50)       # positions open at once, across the group


class NotebookReq(BaseModel):
    name: Optional[str] = Field(None, max_length=80)
    question: Optional[str] = Field(None, max_length=300)
    notes: Optional[str] = Field(None, max_length=4000)
    strategy: Optional[Strategy] = None
    instrument: Optional[str] = Field(None, max_length=60)
    pinned: Optional[bool] = None
    group: Optional[GroupReq] = None
    clearGroup: bool = False


class ImportReq(BaseModel):
    text: str = Field(..., min_length=5, max_length=20000)
    filename: str = Field("", max_length=120)


class ExperimentReq(DataReq):
    label: str = Field("", max_length=120)


class SaveStrategyReq(BaseModel):
    strategy: Strategy
    instrument_token: Optional[int] = None
    instrument: Optional[str] = Field(None, max_length=60)


class AdminPlanReq(BaseModel):
    plan: Literal["free", "basic", "pro"]
    days: int | None = Field(None, ge=1, le=3650)   # None = no end date


class AIReq(BaseModel):
    text: str = Field(..., min_length=5, max_length=2000)


class AlertsReq(BaseModel):
    alerts_enabled: bool = False
    telegram_chat_id: Optional[str] = Field(None, max_length=40, pattern=r"^$|^-?[0-9]{1,20}$|^@[A-Za-z0-9_]{4,32}$")
    alert_email: Optional[str] = Field(None, max_length=200, pattern=r"^$|^[^@\s<>,;\"]+@[^@\s<>,;\"]+\.[A-Za-z]{2,}$")
    daily_report: Optional[bool] = None


class LibraryReq(BaseModel):
    description: str = Field("", max_length=600)
    author: str = Field("", max_length=40)       # a display name; empty means "A StratLab user"


class ReportReq(BaseModel):
    reason: Literal["spam", "offensive", "misleading", "personal", "other"] = "other"


class ScanReq(BaseModel):
    region: Literal["IN", "US"] = "IN"
    set: str = Field("watchlist", max_length=40)          # a preset group id, or "watchlist"


class ScanAlertReq(BaseModel):
    on: bool


class PromoReq(BaseModel):
    days: int = Field(10, ge=1, le=90)


class ModerateReq(BaseModel):
    action: Literal["hide", "restore", "delete"]


class PushKeys(BaseModel):
    p256dh: str = Field(..., max_length=200)
    auth: str = Field(..., max_length=100)


class PushSubscription(BaseModel):
    endpoint: str = Field(..., max_length=1000, pattern=r"^https://")
    keys: PushKeys
    expirationTime: Optional[float] = None


class PushReq(BaseModel):
    subscription: PushSubscription


class PrefsReq(BaseModel):
    level: Literal["new", "some", "pro"] | None = None
    focus: Literal["invest", "trade", "both"] | None = None     # what the user came for: orders menus and suggestions


class IdeasReq(BaseModel):
    q: str = Field(..., min_length=2, max_length=4000)


class SubscribeReq(BaseModel):
    plan: Literal["basic", "pro"]
    period: Literal["month", "year"] = "month"


class VerifyReq(BaseModel):
    razorpay_payment_id: str = Field(..., min_length=1, max_length=64)
    razorpay_subscription_id: str = Field(..., min_length=1, max_length=64)
    razorpay_signature: str = Field(..., min_length=1, max_length=256)


# ---------- options (live paper trading) ----------
class OptLeg(BaseModel):
    side: Literal["sell", "buy"]
    opt: Literal["CE", "PE"]
    offset: float = Field(0, ge=-5000, le=5000)   # distance from the money: + is out of the money, - in the money
    lots: int = Field(1, ge=1, le=50)              # lots of this leg per unit of the structure


class OptTiming(BaseModel):
    entry: str = Field("09:30", pattern=HHMM)       # first entry
    lastEntry: str = Field("14:45", pattern=HHMM)   # no new entries from this time
    squareoff: str = Field("15:15", pattern=HHMM)   # everything closes at this time
    maxEntries: int = Field(1, ge=1, le=20)         # entries a day
    cooldown: int = Field(0, ge=0, le=600)          # minutes to wait after a trade closes


class OptRisk(BaseModel):
    stopType: Literal["none", "amount", "credit_pct"] = "amount"
    stop: float = Field(0, ge=0, le=1e9)            # a loss in money, or % of the premium collected (paid, for debit trades)
    tgtType: Literal["none", "amount", "credit_pct"] = "none"
    tgt: float = Field(0, ge=0, le=1e9)
    trailAfter: float = Field(0, ge=0, le=1e9)      # once the trade is up this much...
    trailBy: float = Field(0, ge=0, le=1e9)         # ...close it if it gives back this much from its best
    legStopPct: float = Field(0, ge=0, le=1000)     # close a sold leg when its premium rises this % above entry
    dailyLoss: float = Field(0, ge=0, le=1e9)       # stop for the day after losing this much


class OptRecenter(BaseModel):
    enabled: bool = False
    every: int = Field(30, ge=5, le=240)            # minutes between checks
    threshold: float = Field(2, ge=0.5, le=50)      # strikes the market has to move from the centre
    roll: Literal["shorts", "all"] = "shorts"       # move only the sold legs, or the whole structure


class OptSizing(BaseModel):
    mode: Literal["lots", "margin"] = "lots"
    lots: int = Field(1, ge=1, le=1000)             # multiplier on every leg's lots
    capital: float = Field(500000, gt=0, le=1e11)   # the paper account; "margin" sizes to fit it
    safety: float = Field(0.98, ge=0.5, le=1)


class OptCosts(BaseModel):
    brokerage: float = Field(20, ge=0, le=1000)     # per order (each freeze-limit slice is an order)
    slippageTicks: int = Field(0, ge=0, le=100)     # ticks worse than the bid or ask
    freeze: int = Field(0, ge=0, le=100000)         # most units in one order; 0 = the exchange default


class OptSignal(BaseModel):
    """Enter when a notebook's rules, run on the underlying's own candles, open a trade; exit when they close it."""
    rules: Strategy
    notebook: Optional[str] = Field(None, max_length=60)
    name: str = Field("", max_length=80)
    short: Literal["mirror", "none"] = "mirror"     # on a short signal: the same legs with calls and puts swapped, or stay out

    @model_validator(mode="after")
    def _intraday(self):
        if self.rules.tf not in ("5m", "15m", "1h"):
            raise ValueError("Option trades close every day, so the rules need 5-minute, 15-minute or hourly candles.")
        return self


class OptionStrategy(BaseModel):
    name: str = Field("Options strategy", max_length=80)
    structure: str = Field("custom", max_length=40)
    exchange: Literal["NFO", "BFO", "MCX"] = "NFO"
    underlying: str = Field(..., min_length=1, max_length=40)
    expiry: str = Field("current", pattern=r"^(current|next|month|\d{4}-\d{2}-\d{2})$")
    offsetUnit: Literal["strikes", "points"] = "strikes"
    legs: list[OptLeg] = Field(..., min_length=1, max_length=8)
    timing: OptTiming = Field(default_factory=OptTiming)
    risk: OptRisk = Field(default_factory=OptRisk)
    recenter: OptRecenter = Field(default_factory=OptRecenter)
    sizing: OptSizing = Field(default_factory=OptSizing)
    costs: OptCosts = Field(default_factory=OptCosts)
    notes: str = Field("", max_length=2000)
    signal: Optional[OptSignal] = None               # None: enter at the set time

    @model_validator(mode="after")
    def _times(self):
        t = self.timing
        if not (t.entry < t.squareoff and t.lastEntry <= t.squareoff):
            raise ValueError("Entries have to come before the square-off time.")
        return self


class OptionStartReq(BaseModel):
    strategy: OptionStrategy


class OptionImportReq(BaseModel):
    text: str = Field(..., min_length=10, max_length=60000)


class FastEntry(BaseModel):
    """Live group options: enter on the price as it moves instead of at candle close, and skip poor fills."""
    ticks: bool = False                                  # check entry rules on the forming candle (India, live ticks)
    maxSpreadPct: float = Field(0, ge=0, le=5)           # skip an entry when bid-ask spread is wider than this % of price (0 = off)
    minPrice: float = Field(0, ge=0, le=1e6)             # skip instruments cheaper than this (0 = off)


class GroupLiveReq(BaseModel):
    strategy: Strategy
    group: GroupReq
    fast: FastEntry = Field(default_factory=FastEntry)


class ShareReq(BaseModel):
    image: Optional[str] = Field(None, max_length=3_000_000)   # the share card as a base64 PNG (data URL or bare)
