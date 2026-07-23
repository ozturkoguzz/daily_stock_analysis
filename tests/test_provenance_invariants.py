"""Provenance-conformance invariants. Each asserts the engine honors input context
(partial / fallback / language). Some fail until the matching phase lands — that failure
is the documented baseline of the 'unhonored data-context' class."""
import re

import pandas as pd

from src.stock_analyzer import StockTrendAnalyzer
from src.agent.orchestrator import _truncate_text


def _frame(closes, vols):
    n = len(closes)
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n, freq="D"),
        "open": [c * 0.999 for c in closes], "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes, "volume": vols,
    })


def complete_frame():
    closes = [100 + i * 0.1 for i in range(40)]
    return _frame(closes, [1_000_000] * 40)


def partial_frame():
    # identical history, but the last bar is a partial intraday bar: tiny volume
    closes = [100 + i * 0.1 for i in range(40)]
    vols = [1_000_000] * 39 + [130_000]      # 13% of the daily average
    df = _frame(closes, vols)
    df.loc[df.index[-1], "is_partial_bar"] = True
    return df


def _has_cjk(s):
    return bool(re.search(r"[一-鿿]", s or ""))


# --- INV-1: partial-bar volume must not be a confirmed shrink/heavy signal ---

def test_INV1_partial_bar_volume_not_confirmed_shrink():
    r = StockTrendAnalyzer().analyze(partial_frame(), "TEST", is_partial_bar=True)
    assert r.volume_status.value not in ("缩量上涨", "缩量回调", "放量上涨", "放量下跌"), \
        "partial-bar volume must not be a confirmed shrink/heavy signal (INV-1)"


def test_INV1_complete_bar_volume_unchanged():
    # Regression guard: the complete-bar path must be identical to today's behavior.
    r_flagged = StockTrendAnalyzer().analyze(complete_frame(), "TEST", is_partial_bar=False)
    r_plain = StockTrendAnalyzer().analyze(complete_frame(), "TEST")
    assert r_flagged.volume_status == r_plain.volume_status
    assert abs(r_flagged.volume_ratio_5d - r_plain.volume_ratio_5d) < 1e-9


# --- INV-5: one_sentence is a single, cleanly-ended sentence ---

def test_INV5_truncation_single_sentence_no_midword():
    text = ("Consolidating within uptrend.\n\nChecklist:\n- a\n- b\n\n"
            "JPM maintains a bullish structure but momentum")
    out = _truncate_text(text, 180)
    assert "\n" not in out, "one_sentence must be a single line (INV-5)"
    body = out[:-1] if out.endswith("…") else out
    assert not body.endswith(" "), "must not end on a dangling space (INV-5)"


def test_INV5_one_sentence_strips_internal_risk_annotation():
    from src.agent.orchestrator import _first_sentence
    out = _first_sentence("[Risk override: hold -> sell] Hold JPM; trend consolidating.")
    assert out == "Hold JPM; trend consolidating."
    assert "Risk override" not in out
