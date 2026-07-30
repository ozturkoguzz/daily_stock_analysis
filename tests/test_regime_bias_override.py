# -*- coding: utf-8 -*-
"""A measured price position outranks the model's own label.

GEHC on 2026-07-30: +12.5% above MA20, at its 20-day high, +12.15% on the day
on 2.5x volume -- routed `sideways` because the technical agent wrote
ma_alignment="neutral". analyze_trend already computes bias_ma20 and nothing
read it.
"""

from types import SimpleNamespace

from src.agent.skills.router import SkillRouter


def _ctx(**raw):
    op = SimpleNamespace(agent_name="technical", raw_data=raw)
    return SimpleNamespace(opinions=[op], meta={})


def test_strong_positive_bias_overrides_a_neutral_label():
    ctx = _ctx(ma_alignment="neutral", trend_score=50, bias_ma20=12.5)
    assert SkillRouter()._detect_regime(ctx) == "trending_up"


def test_strong_negative_bias_overrides_a_neutral_label():
    ctx = _ctx(ma_alignment="neutral", trend_score=50, bias_ma20=-12.5)
    assert SkillRouter()._detect_regime(ctx) == "trending_down"


def test_mild_bias_leaves_the_existing_logic_alone():
    ctx = _ctx(ma_alignment="neutral", trend_score=50, bias_ma20=1.0)
    assert SkillRouter()._detect_regime(ctx) == "sideways"


def test_missing_bias_falls_back_to_the_label():
    ctx = _ctx(ma_alignment="bullish", trend_score=75)
    assert SkillRouter()._detect_regime(ctx) == "trending_up"


def test_bias_does_not_fight_an_agreeing_label():
    ctx = _ctx(ma_alignment="bullish", trend_score=75, bias_ma20=12.5)
    assert SkillRouter()._detect_regime(ctx) == "trending_up"


def test_bias_is_measured_from_the_tool_when_the_opinion_omits_it():
    """The technical agent's JSON carries no bias_ma20 -- its schema is
    signal/confidence/reasoning/key_levels/trend_score/ma_alignment/
    volume_status/pattern. The first implementation read a key that is never
    written, so the override never fired in production."""
    from unittest.mock import patch

    ctx = SimpleNamespace(
        opinions=[SimpleNamespace(agent_name="technical",
                                  raw_data={"ma_alignment": "neutral", "trend_score": 50})],
        meta={}, stock_code="GEHC")
    with patch("src.agent.tools.analysis_tools._handle_analyze_trend",
               return_value={"bias_ma20": 12.47}):
        assert SkillRouter()._detect_regime(ctx) == "trending_up"


def test_tool_failure_falls_back_to_the_label():
    from unittest.mock import patch

    ctx = SimpleNamespace(
        opinions=[SimpleNamespace(agent_name="technical",
                                  raw_data={"ma_alignment": "neutral", "trend_score": 50})],
        meta={}, stock_code="GEHC")
    with patch("src.agent.tools.analysis_tools._handle_analyze_trend",
               side_effect=RuntimeError("network")):
        assert SkillRouter()._detect_regime(ctx) == "sideways"
