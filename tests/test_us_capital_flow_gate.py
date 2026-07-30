# -*- coding: utf-8 -*-
"""A US buy must not be downgraded for missing A-share capital-flow data.

decision_stability downgrades any buy to "Hold and watch" when capital flow is
unavailable. Capital flow is an A-share-only data source, so for every US stock
it is unavailable by definition -- meaning a US stock could NEVER be a buy. 16
US runs hit this downgrade; it is the mechanical reason every US /analyze
returned watch/hold regardless of the setup.

The A-share behaviour is deliberate and must be preserved: for a CN stock,
missing flow is a real red flag and the downgrade stays.
"""

import pytest

from src.analyzer import AnalysisResult, stabilize_decision_with_structure


def _buy_result(code: str) -> AnalysisResult:
    r = AnalysisResult(
        code=code, name="Test", sentiment_score=70,
        trend_prediction="bullish", operation_advice="Buy on the breakout")
    r.decision_type = "buy"
    r.current_price = 100.0
    r.dashboard = {"data_perspective": {"price_position": {
        "current_price": 100.0, "support_level": 95.0, "resistance_level": 110.0}}}
    return r


# Capital flow reports as not_supported for any US ticker -- the real payload.
_US_UNAVAILABLE = {"capital_flow": {"status": "not_supported"}}


def test_us_buy_survives_missing_capital_flow():
    r = _buy_result("JPM")
    stabilize_decision_with_structure(r, fundamental_context=_US_UNAVAILABLE)
    assert r.decision_type == "buy", (
        "a US buy was downgraded for lacking A-share-only capital-flow data")


def test_us_buy_records_flow_as_not_applicable_not_a_red_flag():
    r = _buy_result("AAPL")
    stabilize_decision_with_structure(r, fundamental_context=_US_UNAVAILABLE)
    stability = (r.dashboard or {}).get("decision_stability", {})
    # The calibration simply was not applied; it is not a downgrade reason.
    assert stability.get("applied") is False


def test_cn_buy_is_still_downgraded_when_flow_missing():
    r = _buy_result("600519")  # Kweichow Moutai, an A-share
    stabilize_decision_with_structure(r, fundamental_context=_US_UNAVAILABLE)
    assert r.decision_type == "hold", (
        "A-share flow gate must stay: missing flow is a real red flag for CN")


def test_us_sell_is_untouched_by_the_gate():
    r = _buy_result("JPM")
    r.decision_type = "sell"
    r.operation_advice = "Reduce exposure"
    stabilize_decision_with_structure(r, fundamental_context=_US_UNAVAILABLE)
    assert r.decision_type == "sell"


def test_us_hold_stays_hold():
    r = _buy_result("JPM")
    r.decision_type = "hold"
    r.operation_advice = "Hold and watch"
    stabilize_decision_with_structure(r, fundamental_context=_US_UNAVAILABLE)
    assert r.decision_type == "hold"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
