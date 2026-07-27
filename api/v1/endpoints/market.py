# -*- coding: utf-8 -*-
"""Market session state.

Exists for out-of-process clients (the Telegram bot) that need to know whether
a market is trading before spending LLM or search budget. They cannot import
src.core.trading_calendar, and a hand-rolled calendar on their side would get
holidays wrong, so the calendar answers over HTTP instead.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.v1.schemas.market_session import MarketSessionResponse
from src.core.trading_calendar import build_market_phase_context

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/session",
    response_model=MarketSessionResponse,
    summary="Current market session state",
    description=(
        "Whether the market is trading, which session date applies, and which "
        "daily bar the data actually comes from."
    ),
)
def get_market_session(
    market: str = Query("us", description="Market code: us | cn | hk"),
    at: Optional[str] = Query(
        None,
        description="ISO-8601 instant to evaluate instead of now. Testing/backfill.",
    ),
) -> MarketSessionResponse:
    current_time = None
    if at:
        try:
            current_time = datetime.fromisoformat(at)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail={"error": "invalid_at", "message": f"`at` is not ISO-8601: {at!r}"},
            )

    context = build_market_phase_context(market=market, current_time=current_time)
    return MarketSessionResponse(
        market=context.market,
        session_date=context.session_date.isoformat(),
        effective_daily_bar_date=context.effective_daily_bar_date.isoformat(),
        # A market whose calendar cannot be resolved is treated as trading, so a
        # lookup failure degrades into spending money rather than into silently
        # withholding every user's scheduled push.
        is_trading_day=True if context.is_trading_day is None else context.is_trading_day,
        is_market_open_now=context.is_market_open_now,
        is_partial_bar=context.is_partial_bar,
        phase=context.phase.value,
        market_local_time=context.market_local_time.isoformat(),
    )
