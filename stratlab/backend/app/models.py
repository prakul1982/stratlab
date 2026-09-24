from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

RefType = Literal[
    "price", "num", "sma", "ema", "rsi",
    "macd", "macd_signal", "macd_hist",
    "bb_upper", "bb_mid", "bb_lower",
    "vwap", "supertrend",
    "adx", "stoch_k", "atr_pct", "dc_upper", "dc_lower", "volume", "vol_sma",
]


class Ref(BaseModel):
    t: RefType
    p: Optional[float] = Field(None, ge=1, le=500)   # period (MACD: fast length)
    m: Optional[float] = Field(None, gt=0, le=500)   # MACD slow length, BB std-devs, Supertrend multiplier
    v: Optional[float] = None                         # value when t == "num"

    @model_validator(mode="after")
    def _num_needs_value(self):
        if self.t == "num" and self.v is None:
            raise ValueError("A number in a rule needs a value.")
        return self


class Cond(BaseModel):
    l: Ref
    op: Literal["xa", "xb", "gt", "lt"]
    r: Ref


class Risk(BaseModel):
    capital: float = Field(500000, gt=0, le=1e10)
    riskPct: float = Field(1, gt=0, le=100)
    maxAlloc: float = Field(100, gt=0, le=100)
    sl: float = Field(2, ge=0, lt=100)
    tgt: float = Field(0, ge=0, le=1000)
    brokerage: float = Field(20, ge=0)
    slippage: float = Field(0.05, ge=0, le=5)
    trail: float = Field(0, ge=0, lt=100)       # trailing stop, % below the best price since entry (0 = off)
    maxBars: int = Field(0, ge=0, le=5000)      # close the trade after this many candles (0 = off)


class Strategy(BaseModel):
    name: str = Field("Untitled strategy", max_length=80)
    tf: Literal["1d", "1h", "15m", "5m"] = "1d"
    text: str = Field("", max_length=4000)
    entry: list[Cond] = Field(default_factory=list, max_length=10)
    exit: list[Cond] = Field(default_factory=list, max_length=10)
    entryJoin: Literal["all", "any"] = "all"
    side: Literal["long", "short"] = "long"     # short: sell first, buy back later
    risk: Risk = Field(default_factory=Risk)


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


class BacktestReq(DataReq):
    strategy: Strategy


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


class NotebookReq(BaseModel):
    name: Optional[str] = Field(None, max_length=80)
    question: Optional[str] = Field(None, max_length=300)
    notes: Optional[str] = Field(None, max_length=4000)
    strategy: Optional[Strategy] = None
    instrument: Optional[str] = Field(None, max_length=60)
    pinned: Optional[bool] = None


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
    telegram_chat_id: Optional[str] = Field(None, max_length=40)
    alert_email: Optional[str] = Field(None, max_length=200)


class SubscribeReq(BaseModel):
    plan: Literal["basic", "pro"]


class VerifyReq(BaseModel):
    razorpay_payment_id: str
    razorpay_subscription_id: str
    razorpay_signature: str
