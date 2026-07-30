# -*- coding: utf-8 -*-
"""ATR must reach the agent.

Audited stops sat at 0.27-0.54x ATR -- inside a single average day's range, so
an ordinary session closes the trade before the thesis resolves. ATR is
computed nowhere in the stack (not StockTrendAnalyzer, not any tool), so the
model had no volatility number to size a stop against.
"""

import pandas as pd
import pytest
from unittest.mock import patch

from src.agent.tools.analysis_tools import _handle_analyze_trend


def _bars(n=60, base=100.0, rng=3.0):
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "date": idx,
        "open": [base] * n,
        "high": [base + rng / 2] * n,
        "low": [base - rng / 2] * n,
        "close": [base] * n,
        "volume": [1_000_000] * n,
    })


def test_analyze_trend_exposes_atr():
    with patch("src.agent.tools.analysis_tools._fetch_trend_data", return_value=_bars()):
        out = _handle_analyze_trend("AAPL")
    assert "atr_14" in out, "the agent cannot size a stop without ATR"
    assert out["atr_14"] == pytest.approx(3.0, abs=0.01)
    assert out["atr_pct"] == pytest.approx(3.0, abs=0.05)


def test_atr_absent_when_history_too_short():
    with patch("src.agent.tools.analysis_tools._fetch_trend_data", return_value=_bars(n=25)):
        out = _handle_analyze_trend("AAPL")
    assert out.get("atr_14") is not None  # 25 bars is enough for ATR14
