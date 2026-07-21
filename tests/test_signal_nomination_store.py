from sqlalchemy import create_engine
from src.services import signal_nomination_store as store


def _engine():
    e = create_engine("sqlite://")  # in-memory
    store.ensure_table(e)
    return e


def _nom(ticker, rule="breakout", entry=100.0, strength=75):
    return {"ticker": ticker, "rule": rule, "trend_status": "多头排列",
            "trend_strength": strength, "signal_score": 70, "vol_ratio": 2.5,
            "off_20d_high_pct": 0.5, "rsi6": 60.0, "entry_close": entry}


def test_persist_is_idempotent_per_date_ticker_rule():
    e = _engine()
    assert store.persist_nominations(e, "2026-07-20", [_nom("NVDA")]) == 1
    assert store.persist_nominations(e, "2026-07-20", [_nom("NVDA")]) == 0  # dup ignored
    assert len(store.list_for_date(e, "2026-07-20")) == 1


def test_tickers_for_date_filters_by_rule():
    e = _engine()
    store.persist_nominations(e, "2026-07-20", [_nom("NVDA", "breakout"), _nom("MU", "oversold")])
    assert store.tickers_for_date(e, "2026-07-20", "breakout") == {"NVDA"}


def test_grade_pending_writes_forward_returns():
    e = _engine()
    store.persist_nominations(e, "2026-07-20", [_nom("NVDA", entry=100.0)])

    def price_lookup(ticker, session_date, horizon):
        return 110.0 if horizon == 20 else 105.0

    assert store.grade_pending(e, price_lookup) == 1
    row = store.list_for_ticker(e, "NVDA")[0]
    assert abs(row["ret_20d"] - 0.10) < 1e-6
    assert abs(row["ret_5d"] - 0.05) < 1e-6
