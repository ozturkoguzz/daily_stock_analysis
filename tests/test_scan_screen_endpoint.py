# -*- coding: utf-8 -*-
"""Tests for POST /api/v1/scan/screen.

Backs the bot's daily watchlist digest. The digest replaced a per-ticker LLM
/analyze (~$0.113 and ~5 Tavily searches each, of which the push then discarded
about 90%) with a $0 deterministic screen. It must describe EVERY requested
ticker, not just the ones that trip a rule -- a watchlist digest that silently
omits your quiet names is not a digest.

It deliberately reuses the /signals engine so the digest cannot drift from what
the signals board says about the same stock on the same day.
"""

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1 import endpoints
from api.v1.router import router as api_router


def _frame(closes, volumes=None, start="2026-01-01"):
    n = len(closes)
    volumes = volumes or [1_000_000] * n
    dates = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame({
        "date": dates,
        "open": [c * 0.99 for c in closes],
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.98 for c in closes],
        "close": closes,
        "volume": volumes,
    })


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    return TestClient(app)


@pytest.fixture()
def fake_history(monkeypatch):
    """Patch the batch download so no test touches the network."""
    store = {}

    def fake_download(tickers):
        return {t: store[t] for t in tickers if t in store}

    monkeypatch.setattr(endpoints.scan, "download_history", fake_download)
    return store


def test_every_requested_ticker_comes_back(client, fake_history) -> None:
    rising = [100 + i for i in range(80)]
    falling = [200 - i for i in range(80)]
    fake_history["AAA"] = _frame(rising)
    fake_history["BBB"] = _frame(falling)

    body = client.post("/api/v1/scan/screen", json={"tickers": ["AAA", "BBB"]})
    assert body.status_code == 200, body.text
    rows = body.json()["rows"]
    assert {r["ticker"] for r in rows} == {"AAA", "BBB"}


def test_a_quiet_ticker_is_described_with_no_hits(client, fake_history) -> None:
    flat = [100.0] * 80
    fake_history["AAA"] = _frame(flat)

    rows = client.post("/api/v1/scan/screen", json={"tickers": ["AAA"]}).json()["rows"]
    assert len(rows) == 1
    assert rows[0]["hits"] == []
    assert rows[0]["entry_close"] is not None


def test_row_carries_the_fields_the_digest_renders(client, fake_history) -> None:
    fake_history["AAA"] = _frame([100 + i for i in range(80)])
    row = client.post("/api/v1/scan/screen", json={"tickers": ["AAA"]}).json()["rows"][0]
    for field in ("ticker", "trend_status", "rsi6", "vol_ratio",
                  "off_20d_high_pct", "entry_close", "change_pct", "hits"):
        assert field in row, f"digest needs {field}"


def test_change_pct_is_measured_against_the_prior_close(client, fake_history) -> None:
    closes = [100.0] * 79 + [110.0]
    fake_history["AAA"] = _frame(closes)
    row = client.post("/api/v1/scan/screen", json={"tickers": ["AAA"]}).json()["rows"][0]
    assert row["change_pct"] == pytest.approx(10.0, abs=0.01)


def test_a_dead_ticker_does_not_kill_the_batch(client, fake_history) -> None:
    fake_history["AAA"] = _frame([100 + i for i in range(80)])
    # BBB is absent from the download result entirely.
    rows = client.post("/api/v1/scan/screen", json={"tickers": ["AAA", "BBB"]}).json()["rows"]
    assert [r["ticker"] for r in rows] == ["AAA"]


def test_a_ticker_with_too_little_history_is_skipped_not_fatal(client, fake_history) -> None:
    fake_history["AAA"] = _frame([100 + i for i in range(80)])
    fake_history["NEW"] = _frame([50.0] * 10)  # below MIN_ROWS
    rows = client.post("/api/v1/scan/screen", json={"tickers": ["AAA", "NEW"]}).json()["rows"]
    assert [r["ticker"] for r in rows] == ["AAA"]


def test_empty_ticker_list_is_rejected(client) -> None:
    assert client.post("/api/v1/scan/screen", json={"tickers": []}).status_code == 422


def test_oversized_ticker_list_is_rejected(client) -> None:
    # 50 is the elite watchlist limit; beyond that something is wrong upstream.
    payload = {"tickers": [f"T{i}" for i in range(51)]}
    assert client.post("/api/v1/scan/screen", json=payload).status_code == 422


def test_screen_makes_exactly_one_batched_download(client, monkeypatch) -> None:
    calls = []

    def fake_download(tickers):
        calls.append(list(tickers))
        return {t: _frame([100 + i for i in range(80)]) for t in tickers}

    monkeypatch.setattr(endpoints.scan, "download_history", fake_download)
    client.post("/api/v1/scan/screen", json={"tickers": ["AAA", "BBB", "CCC"]})
    assert len(calls) == 1, "the digest must not download per ticker"
    assert calls[0] == ["AAA", "BBB", "CCC"]
