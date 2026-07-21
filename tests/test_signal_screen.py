import pandas as pd
from src.services.signal_screen import screen_one, NDX_100


def _frame(closes, vols, opens=None):
    n = len(closes)
    opens = opens or [c * 0.999 for c in closes]  # green-ish
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n, freq="D"),
        "open": opens, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes, "volume": vols,
    })


def test_universe_is_nonempty_and_deduped():
    assert len(NDX_100) >= 90
    assert len(NDX_100) == len(set(NDX_100))


def test_breakout_fires_on_bullish_new_high_high_volume():
    # steady uptrend so MA5>MA10>MA20 (bullish), last close = 20d high, volume spike
    closes = [100 + i for i in range(80)]
    vols = [1_000_000] * 79 + [3_000_000]  # last day ~3x the 5d avg
    hits = {h["rule"] for h in screen_one(_frame(closes, vols), "TEST")}
    assert "breakout" in hits


def test_oversold_fires_on_rsi6_below_15():
    # long uptrend then a sharp multi-day drop drives RSI6 under 15
    closes = [100 + i for i in range(70)] + [169, 160, 151, 143, 136, 130, 125, 121, 118, 116]
    vols = [1_000_000] * 80
    hits = {h["rule"] for h in screen_one(_frame(closes, vols), "TEST")}
    assert "oversold" in hits


def test_no_breakout_when_far_below_high():
    # bullish but last close well under the 20d high -> not a breakout
    closes = [100 + i for i in range(78)] + [176, 150]  # last day gaps down 15%
    vols = [1_000_000] * 79 + [3_000_000]
    hits = {h["rule"] for h in screen_one(_frame(closes, vols), "TEST")}
    assert "breakout" not in hits
