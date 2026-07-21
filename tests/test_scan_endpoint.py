import datetime

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import api.v1.endpoints.scan as scan
from src.services import signal_nomination_store as store


def _mem_engine():
    # Shared in-memory DB across threads (TestClient runs the endpoint in a
    # threadpool); StaticPool keeps one connection so persist is visible to the test.
    return create_engine("sqlite://", connect_args={"check_same_thread": False},
                         poolclass=StaticPool)


def _uptrend_frame():
    closes = [100 + i for i in range(80)]
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=80, freq="D"),
        "open": [c * 0.999 for c in closes], "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes,
        "volume": [1_000_000] * 79 + [3_000_000],
    })


def _client():
    app = FastAPI()
    app.include_router(scan.router, prefix="/api/v1/scan")
    return TestClient(app)


def test_nominate_screens_persists_and_flags_new():
    engine = _mem_engine()
    store.ensure_table(engine)
    with patch.object(scan, "_engine", return_value=engine), \
         patch.object(scan, "download_history", return_value={"NVDA": _uptrend_frame()}), \
         patch.object(scan, "NDX_100", ["NVDA"]), \
         patch.object(scan, "get_effective_trading_date", return_value=datetime.date(2026, 7, 20)):
        r = _client().get("/api/v1/scan/nominate")
    assert r.status_code == 200
    body = r.json()
    assert body["session_date"] == "2026-07-20"
    bo = body["groups"]["breakout"]
    assert bo and bo[0]["ticker"] == "NVDA" and bo[0]["is_new"] is True
    assert store.tickers_for_date(engine, "2026-07-20", "breakout") == {"NVDA"}


def test_history_returns_calls_with_live_return():
    engine = _mem_engine()
    store.ensure_table(engine)
    store.persist_nominations(engine, "2026-07-16",
        [{"ticker": "NVDA", "rule": "breakout", "trend_status": "强势多头",
          "trend_strength": 90, "signal_score": 80, "vol_ratio": 3.0,
          "off_20d_high_pct": 0.1, "rsi6": 65.0, "entry_close": 100.0}])
    with patch.object(scan, "_engine", return_value=engine), \
         patch.object(scan, "_latest_close", return_value=110.0):
        r = _client().get("/api/v1/scan/history", params={"ticker": "NVDA"})
    assert r.status_code == 200
    call = r.json()["calls"][0]
    assert call["rule"] == "breakout" and abs(call["return_pct"] - 10.0) < 1e-6


def test_track_record_aggregates_graded_rows():
    engine = _mem_engine()
    store.ensure_table(engine)
    store.persist_nominations(engine, "2026-06-01",
        [{"ticker": "NVDA", "rule": "breakout", "trend_status": "多头排列",
          "trend_strength": 75, "signal_score": 70, "vol_ratio": 2.5,
          "off_20d_high_pct": 0.5, "rsi6": 60.0, "entry_close": 100.0}])
    store.grade_pending(engine, lambda t, d, h: 120.0 if h == 20 else 105.0)
    with patch.object(scan, "_engine", return_value=engine):
        r = _client().get("/api/v1/scan/track-record")
    rec = {x["rule"]: x for x in r.json()["rules"]}
    assert rec["breakout"]["n"] == 1 and abs(rec["breakout"]["mean_20d_pct"] - 20.0) < 1e-6
