"""$0 technical screen for the /signals board. Two locked rules (validated 2026-07-21):
breakout (bullish + near 20d high + volume) and oversold bounce (RSI6<15). No LLM."""
from __future__ import annotations

from typing import Dict, List, Optional

from src.stock_analyzer import StockTrendAnalyzer

# Validated 2026-07-17 (present in DSA US universe + >=60 rows yfinance). Re-validate on
# index rebalances. Kept in sync with scripts/scan_universe.py.
NDX_100: List[str] = [
    "ADBE", "AMD", "ABNB", "ALNY", "GOOGL", "GOOG", "AMZN", "AEP", "AMGN", "ADI",
    "AAPL", "AMAT", "APP", "ARM", "ASML", "ALAB", "ADSK", "ADP", "AXON", "BKR",
    "BKNG", "AVGO", "CDNS", "CTAS", "CSCO", "CCEP", "CMCSA", "CEG", "CPRT",
    "CRWV", "COST", "CRWD", "CSX", "DDOG", "DXCM", "FANG", "DASH", "EA", "EXC",
    "FAST", "FER", "FTNT", "GEHC", "GILD", "HON", "IDXX", "INTC", "INTU", "ISRG",
    "KDP", "KLAC", "KHC", "LRCX", "LIN", "LITE", "MAR", "MRVL", "MELI", "META",
    "MCHP", "MU", "MSFT", "MSTR", "MDLZ", "MPWR", "MNST", "NBIS", "NFLX", "NVDA",
    "NXPI", "ORLY", "ODFL", "PCAR", "PLTR", "PANW", "PAYX", "PYPL", "PDD", "PEP",
    "QCOM", "REGN", "RKLB", "ROP", "ROST", "SNDK", "STX", "SHOP", "SBUX", "SNPS",
    "TMUS", "TTWO", "TER", "TSLA", "TXN", "TRI", "VRTX", "WMT", "WBD", "WDC",
    "WDAY", "XEL",
]

MIN_ROWS = 60
_ANALYZER = StockTrendAnalyzer()


def describe_one(df, ticker: str) -> Optional[Dict]:
    """Describe one ticker: its metrics plus which rules it trips (possibly none).

    The watchlist digest needs a row for every name a user follows, not only the
    ones that nominate, so the measuring lives here and screen_one() selects from
    it. Keeping one implementation is deliberate: the digest and the /signals
    board must never disagree about the same stock on the same day.

    Returns None when there is not enough history to measure.
    """
    if df is None or len(df) < MIN_ROWS:
        return None
    r = _ANALYZER.analyze(df, ticker)
    close = df["close"].astype(float)
    high_20 = float(close.tail(20).max())
    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    off_high = (high_20 - last) / high_20 * 100 if high_20 else 0.0
    vol = float(r.volume_ratio_5d or 0.0)
    rsi6 = float(r.rsi_6 or 50.0)
    status = r.trend_status.value
    bullish = "多头" in status
    near_high = last >= 0.98 * high_20

    hits: List[str] = []
    if bullish and near_high and vol >= 2.0:
        hits.append("breakout")
    if rsi6 < 15.0:
        hits.append("oversold")

    return {
        "ticker": ticker, "trend_status": status, "trend_strength": r.trend_strength,
        "signal_score": r.signal_score, "vol_ratio": round(vol, 2),
        "off_20d_high_pct": round(off_high, 1), "rsi6": round(rsi6, 1),
        "entry_close": round(last, 4),
        "change_pct": round((last - prev) / prev * 100, 2) if prev else 0.0,
        "hits": hits,
    }


def screen_one(df, ticker: str) -> List[Dict]:
    """Return 0..2 nomination dicts for one ticker. Columns must be lowercased OHLCV."""
    described = describe_one(df, ticker)
    if described is None:
        return []
    common = {k: v for k, v in described.items() if k not in ("hits", "change_pct")}
    return [{**common, "rule": rule} for rule in described["hits"]]
