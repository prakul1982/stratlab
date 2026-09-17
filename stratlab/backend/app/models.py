from typing import Literal, Optional
from pydantic import BaseModel, Field

RefType = Literal[
    "price", "num", "sma", "ema", "rsi",
    "macd", "macd_signal", "macd_hist",
    "bb_upper", "bb_mid", "bb_lower",
    "vwap", "supertrend",
]


class Ref(BaseModel):
    t: RefType
    p: Optional[float] = Field(None, ge=1, le=500)   # period (MACD: fast length)
    m: Optional[float] = Field(None, gt=0, le=500)   # MACD slow length, BB std-devs, Supertrend multiplier
    v: Optional[float] = None                         # value when t == "num"


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


class Strategy(BaseModel):
    name: str = Field("Untitled strategy", max_length=80)
    tf: Literal["1d", "1h", "15m", "5m"] = "1d"
    text: str = Field("", max_length=4000)
    entry: list[Cond] = Field(default_factory=list, max_length=10)
    exit: list[Cond] = Field(default_factory=list, max_length=10)
    entryJoin: Literal["all", "any"] = "all"
    risk: Risk = Field(default_factory=Risk)


class BacktestReq(BaseModel):
    strategy: Strategy
    instrument_token: int
    days: int = Field(365, ge=5, le=3650)


class LiveStartReq(BaseModel):
    strategy: Strategy
    instrument_token: int


class SaveStrategyReq(BaseModel):
    strategy: Strategy
    instrument_token: Optional[int] = None


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
