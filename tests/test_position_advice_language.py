# -*- coding: utf-8 -*-
"""Regression tests for language-aware position-advice fallbacks."""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.agent.orchestrator import AgentOrchestrator, _default_position_advice
from src.agent.protocols import AgentContext


class TestDefaultPositionAdviceLanguage(unittest.TestCase):
    def test_sell_advice_localized_to_english(self):
        advice = _default_position_advice("sell", "en")
        self.assertEqual(advice["no_position"], "Stay out for now; wait for risk to fully play out.")
        self.assertEqual(advice["has_position"], "Prioritize drawdown control; reduce or exit per plan.")

    def test_sell_advice_defaults_to_chinese(self):
        advice = _default_position_advice("sell", "zh")
        self.assertEqual(advice["no_position"], "暂不参与，等待风险充分释放。")
        self.assertEqual(advice["has_position"], "优先控制回撤，按计划减仓或离场。")

    def test_normalize_dashboard_payload_uses_english_position_advice(self):
        orch = AgentOrchestrator(
            tool_registry=MagicMock(),
            llm_adapter=MagicMock(),
        )
        ctx = AgentContext(query="test", stock_code="AAPL", stock_name="Apple")
        ctx.meta["report_language"] = "en"

        payload = {
            "decision_type": "sell",
            "analysis_summary": "Momentum is weakening.",
        }

        normalized = orch._normalize_dashboard_payload(payload, ctx)

        position_advice = normalized["dashboard"]["core_conclusion"]["position_advice"]
        self.assertEqual(
            position_advice["no_position"],
            "Stay out for now; wait for risk to fully play out.",
        )
        self.assertNotIn("暂不参与", position_advice["no_position"])


if __name__ == "__main__":
    unittest.main()
