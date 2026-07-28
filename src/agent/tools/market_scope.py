# -*- coding: utf-8 -*-
"""Market-aware tool filtering.

Some tools only have A-share data behind them. Offering them on a US analysis
costs a real agent step for a guaranteed failure:

    Agent requesting 1 tool call(s): ['get_chip_distribution']
    [筹码分布] HIMS 所有数据源均失败
    Agent step 6/6

and 28 production runs logged "Agent hit max steps" -- analyses truncated while
budget was spent on tools that cannot return anything. Dropping them from the
offered set is cheaper and more honest than letting the model discover this one
failed call at a time.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, List, Optional

logger = logging.getLogger(__name__)

# Verified live against US tickers before adding each one:
#   get_capital_flow('MRVL')      -> status=not_supported,
#                                    "Capital flow data is only available for A-share stocks"
#   get_chip_distribution('MRVL') -> "No chip distribution data available for MRVL"
#   get_sector_rankings()         -> Chinese sector names (体育, 酒、饮料和精制茶制造业),
#                                    and the tool takes no region parameter at all
CN_ONLY_TOOLS = {
    "get_chip_distribution",
    "get_capital_flow",
    "get_sector_rankings",
}


def market_for_scope(stock_scope: Any) -> Optional[str]:
    """Resolve the single market a run is scoped to, or None if not decidable.

    Returns None for an absent, empty or mixed-market scope so callers fail
    open -- losing a usable tool is worse than offering one that will fail.
    """
    codes = getattr(stock_scope, "allowed_stock_codes", None) or ()
    if not codes:
        return None

    from src.core.trading_calendar import get_market_for_stock
    # Codes reach the scope in several shapes (SH600519, 600519.SH, 600519);
    # normalise first, exactly as the analysis pipeline does.
    from data_provider.base import normalize_stock_code

    markets = {get_market_for_stock(normalize_stock_code(str(code))) for code in codes}
    markets.discard(None)
    if len(markets) != 1:
        return None
    return markets.pop()


def tools_for_market(tools: Iterable[Any], market: Optional[str]) -> List[Any]:
    """Drop tools that have no data source for `market`.

    `market=None` keeps everything: an unresolved market must never silently
    shrink the agent's capabilities.
    """
    tool_list = list(tools)
    if market is None or market == "cn":
        return tool_list

    kept = [t for t in tool_list if getattr(t, "name", None) not in CN_ONLY_TOOLS]
    dropped = len(tool_list) - len(kept)
    if dropped:
        logger.info(
            "[ToolScope] market=%s: withheld %d A-share-only tool(s) from the agent",
            market, dropped,
        )
    return kept
