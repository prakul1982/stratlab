/* The ready-made trend scans as the server lists them (app/scan_presets.py listing()), so /research/scan draws every scan's chip and the
 * picked scan's rule at once, before /research/scan/sets answers (LIVE18B-009: two chips, then nine, moved the group, the Scan button and the
 * note down at 7.6 s; phone CLS 0.099). The server's list replaces it when it comes; backend tests/test_site81.py keeps the two equal. */
export const SCAN_LIST: { id: string; name: string; text: string; rules: string[]; within: number }[] = [
  {
    "id": "st_s2",
    "name": "Stage 2 + Supertrend",
    "text": "The price is above a rising 150-day average (Stage 2) and above the Supertrend (10 days, 3 times the average daily range).",
    "rules": [
      "Stage is 2",
      "Price is above Supertrend 10,3"
    ],
    "within": 1
  },
  {
    "id": "high52",
    "name": "52-week high breakout",
    "text": "The close went above the highest high of the previous 252 trading days (about 52 weeks).",
    "rules": [
      "Price crosses above Donchian high 252"
    ],
    "within": 3
  },
  {
    "id": "golden_cross",
    "name": "Golden cross (50/200)",
    "text": "The 50-day average crossed above the 200-day average.",
    "rules": [
      "SMA 50 crosses above SMA 200"
    ],
    "within": 5
  },
  {
    "id": "rsi_bounce",
    "name": "RSI oversold bounce",
    "text": "The 14-day RSI crossed back above 30, after closing at or below it.",
    "rules": [
      "RSI 14 crosses above 30"
    ],
    "within": 3
  },
  {
    "id": "volume_surge",
    "name": "Volume surge",
    "text": "Volume was more than 2 times its average of the 20 days before, and the close was above the previous close.",
    "rules": [
      "Volume is above 2 × Volume SMA 20 1 candle ago",
      "Price is above Price 1 candle ago"
    ],
    "within": 1
  },
  {
    "id": "bb_squeeze",
    "name": "Bollinger squeeze breakout",
    "text": "The close went above the upper Bollinger band (20 days, 2 standard deviations) the day after the bands' width was in the narrowest 20% of the last 120 days.",
    "rules": [
      "Price crosses above BB upper 20,2",
      "the bands' width the day before was in the narrowest 20% of the last 120 days"
    ],
    "within": 3
  },
  {
    "id": "near_low52",
    "name": "Near 52-week low",
    "text": "The close is within 5% of the lowest low of the previous 252 trading days, or below it.",
    "rules": [
      "Price is below 1.05 × Donchian low 252"
    ],
    "within": 1
  },
  {
    "id": "pullback",
    "name": "Pullback in an uptrend",
    "text": "The 50-day average is above the 200-day average and the close is above the 50-day, but below the 20-day exponential average (EMA).",
    "rules": [
      "SMA 50 is above SMA 200",
      "Price is above SMA 50",
      "Price is below EMA 20"
    ],
    "within": 1
  }
];
