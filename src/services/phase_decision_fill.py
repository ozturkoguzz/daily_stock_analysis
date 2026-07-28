# -*- coding: utf-8 -*-
"""Fill phase_decision fields the run already knows.

The agent path does not retry the LLM on a failed integrity check, so any
mandatory field the model omits ships as "Model did not provide ...". Measured:
131 analyses, 116 of them missing the same three fields.

Two of the three never needed the model:

* ``phase_context`` must be a dict, and ``build_market_phase_context()``
  produced exactly that dict earlier in the same run.
* ``data_limitations`` must be a list of what the analysis could not see. That
  is run state -- a stale daily bar, a forming bar, news that was never
  retrieved -- and stating it from facts beats asking a model to remember it.

``watch_conditions`` is a judgement call and is deliberately left to the model.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_PHASE_CONTEXT_KEYS = (
    "market", "phase", "session_date", "effective_daily_bar_date",
    "is_trading_day", "is_market_open_now", "is_partial_bar",
)


def _known_limitations(phase_context: Dict[str, Any], has_news: bool) -> List[str]:
    """Only statements that are verifiably true for this run."""
    limits: List[str] = []

    session = str(phase_context.get("session_date") or "")
    bar = str(phase_context.get("effective_daily_bar_date") or "")
    if bar and session and bar < session:
        limits.append(
            f"Based on the {bar} session close; the {session} bar was not complete "
            "at analysis time."
        )
    if phase_context.get("is_partial_bar") is True:
        limits.append("Today's daily bar is still forming and is not yet closed.")
    if not has_news:
        limits.append("No news coverage was retrieved for this analysis.")
    return limits


def fill_known_phase_decision_fields(
    result: Any,
    phase_context: Optional[Dict[str, Any]],
    *,
    has_news: bool = True,
) -> List[str]:
    """Populate phase_decision fields derivable from run state, in place.

    Never overwrites anything the model supplied -- a model-authored field is
    the real answer and this is only a floor. Returns the list of field paths
    that were filled, so the caller can subtract them from the integrity
    check's missing set.
    """
    if not isinstance(phase_context, dict) or not phase_context:
        return []

    dashboard = getattr(result, "dashboard", None)
    if not isinstance(dashboard, dict):
        return []

    phase_decision = dashboard.get("phase_decision")
    if not isinstance(phase_decision, dict):
        phase_decision = {}
        dashboard["phase_decision"] = phase_decision

    filled: List[str] = []

    if not isinstance(phase_decision.get("phase_context"), dict):
        phase_decision["phase_context"] = {
            k: phase_context.get(k) for k in _PHASE_CONTEXT_KEYS
            if phase_context.get(k) is not None
        }
        filled.append("dashboard.phase_decision.phase_context")

    if not isinstance(phase_decision.get("data_limitations"), list):
        # A clean session legitimately has nothing to declare; the field still
        # has to exist as a list, and an empty one is the honest value.
        phase_decision["data_limitations"] = _known_limitations(phase_context, has_news)
        filled.append("dashboard.phase_decision.data_limitations")

    if filled:
        logger.info("[PhaseDecision] filled from run state: %s", filled)
    return filled
