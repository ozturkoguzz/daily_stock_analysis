# -*- coding: utf-8 -*-
"""DataContext — the single source of truth for input provenance.

Every consumer that makes a signal/render/decision on market data should read provenance
from here rather than doing ad-hoc dict lookups, so no consumer silently ignores that the
data is partial / fallback / A-share-shaped / a non-English target. The pieces already
exist scattered across ``market_phase_summary``, ``realtime_quote.source`` and the report
language; this consolidates them into one typed, honored descriptor.

The invariants in ``tests/test_provenance_invariants.py`` are the enforcement contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class DataContext:
    market: str            # us / cn / hk / jp / kr / ""
    session_phase: str     # premarket / intraday / postmarket / non_trading / unknown
    is_partial_bar: bool   # latest bar is a forming intraday candle
    quote_source: str      # realtime / fallback / stale / unknown
    report_language: str   # en / zh / ko

    @property
    def bar_complete(self) -> bool:
        return not self.is_partial_bar

    @property
    def is_us(self) -> bool:
        return self.market == "us"


def _text(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ""


def resolve_data_context(
    market_phase_summary: Optional[Dict[str, Any]],
    realtime_quote: Optional[Dict[str, Any]],
    report_language: Optional[str],
) -> DataContext:
    """Build the provenance descriptor from the runtime inputs. All inputs optional."""
    mps = market_phase_summary if isinstance(market_phase_summary, dict) else {}
    rq = realtime_quote if isinstance(realtime_quote, dict) else {}

    lang = _text(report_language)
    lang = lang if lang in {"en", "zh", "ko"} else "zh"

    return DataContext(
        market=_text(mps.get("market")),
        session_phase=_text(mps.get("phase")) or "unknown",
        is_partial_bar=bool(mps.get("is_partial_bar")),
        quote_source=_text(rq.get("source")) or "unknown",
        report_language=lang,
    )


__all__ = ["DataContext", "resolve_data_context"]
