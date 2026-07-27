# -*- coding: utf-8 -*-
"""Tests for GET /api/v1/market/session.

The Telegram bot runs in a separate process and cannot import
src.core.trading_calendar, which is backed by exchange_calendars (real holiday
data). Without this endpoint the bot would have to reimplement a market
calendar, and it would get holidays wrong. Scheduled jobs use it to skip
non-trading days instead of spending LLM and Tavily budget on stale bars.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from api.v1.router import router as api_router
from fastapi import FastAPI


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    return TestClient(app)


def _get(client: TestClient, **params):
    response = client.get("/api/v1/market/session", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_saturday_is_not_a_trading_day(client: TestClient) -> None:
    # 2026-07-25 is a Saturday. The daily push fired on this date and paid for
    # a full LLM analysis of Friday's bars.
    at = datetime(2026, 7, 25, 12, 0, tzinfo=ZoneInfo("America/New_York")).isoformat()
    body = _get(client, market="us", at=at)
    assert body["is_trading_day"] is False
    assert body["market"] == "us"


def test_sunday_is_not_a_trading_day(client: TestClient) -> None:
    at = datetime(2026, 7, 26, 12, 0, tzinfo=ZoneInfo("America/New_York")).isoformat()
    assert _get(client, market="us", at=at)["is_trading_day"] is False


def test_midweek_session_is_a_trading_day(client: TestClient) -> None:
    # Wednesday 2026-07-22, mid-session.
    at = datetime(2026, 7, 22, 12, 0, tzinfo=ZoneInfo("America/New_York")).isoformat()
    body = _get(client, market="us", at=at)
    assert body["is_trading_day"] is True
    assert body["phase"] == "intraday"


def test_response_carries_the_bar_the_data_actually_comes_from(client: TestClient) -> None:
    # Monday premarket: the newest complete daily bar is still Friday's. This is
    # the field that lets a report say which session it is really based on.
    at = datetime(2026, 7, 27, 4, 0, tzinfo=ZoneInfo("America/New_York")).isoformat()
    body = _get(client, market="us", at=at)
    assert body["effective_daily_bar_date"] == "2026-07-24"
    assert body["phase"] == "premarket"


def test_defaults_to_us_and_now(client: TestClient) -> None:
    body = _get(client)
    assert body["market"] == "us"
    assert "session_date" in body
    assert isinstance(body["is_trading_day"], bool)


def test_unparseable_at_is_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/market/session", params={"at": "not-a-time"})
    assert response.status_code == 422
