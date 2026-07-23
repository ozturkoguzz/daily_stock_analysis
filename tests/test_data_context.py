"""DataContext: one typed descriptor consolidating the scattered provenance flags
(market, session phase, bar completeness, quote source, language) so every consumer
reads provenance from a single source instead of ad-hoc dict lookups."""
from src.core.data_context import DataContext, resolve_data_context


def test_resolves_intraday_partial_fallback():
    ctx = resolve_data_context(
        market_phase_summary={"market": "us", "phase": "intraday", "is_partial_bar": True},
        realtime_quote={"source": "fallback"},
        report_language="en",
    )
    assert ctx.market == "us"
    assert ctx.session_phase == "intraday"
    assert ctx.is_partial_bar is True
    assert ctx.bar_complete is False
    assert ctx.quote_source == "fallback"
    assert ctx.report_language == "en"


def test_resolves_premarket_complete_realtime_defaults():
    ctx = resolve_data_context(
        market_phase_summary={"market": "cn", "phase": "premarket", "is_partial_bar": False},
        realtime_quote={"source": "realtime"},
        report_language="zh",
    )
    assert ctx.is_partial_bar is False
    assert ctx.bar_complete is True
    assert ctx.session_phase == "premarket"


def test_missing_inputs_are_safe():
    ctx = resolve_data_context(None, None, None)
    assert isinstance(ctx, DataContext)
    assert ctx.is_partial_bar is False
    assert ctx.market == ""
    assert ctx.quote_source == "unknown"
    assert ctx.report_language == "zh"
