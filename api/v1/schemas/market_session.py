# -*- coding: utf-8 -*-
"""Schema for GET /api/v1/market/session."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MarketSessionResponse(BaseModel):
    """Whether a market is trading, and which bar its data comes from."""

    market: Optional[str] = Field(None, description="Market code")
    session_date: str = Field(..., description="Session date the market is on (ISO date)")
    effective_daily_bar_date: str = Field(
        ..., description="Newest complete daily bar available (ISO date)"
    )
    is_trading_day: bool = Field(..., description="Whether this is a trading session")
    is_market_open_now: Optional[bool] = Field(None, description="Regular session open right now")
    is_partial_bar: Optional[bool] = Field(None, description="Today's bar is still forming")
    phase: str = Field(..., description="premarket|intraday|postmarket|non_trading|unknown")
    market_local_time: str = Field(..., description="Evaluated instant in market-local time")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "market": "us",
            "session_date": "2026-07-24",
            "effective_daily_bar_date": "2026-07-24",
            "is_trading_day": False,
            "is_market_open_now": False,
            "is_partial_bar": False,
            "phase": "non_trading",
            "market_local_time": "2026-07-25T12:00:00-04:00",
        }
    })
