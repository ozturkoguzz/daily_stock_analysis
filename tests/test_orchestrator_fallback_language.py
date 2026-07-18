# -*- coding: utf-8 -*-
"""Regression tests for language-aware orchestrator fallback synthesizers.

Covers the multi-agent-path Chinese leaks fixed alongside the notification/
history_service ma_alignment translation gap: the "no complete dashboard"
summary, default time-sensitivity, signal_type badge, position-size wording,
battle-plan risk_control label, and the risk-override rewrite of
signal_type/one_sentence/position_advice/risk_warning/analysis_summary.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.agent.orchestrator import AgentOrchestrator
from src.agent.protocols import AgentContext, AgentOpinion


def _make_orchestrator() -> AgentOrchestrator:
    return AgentOrchestrator(tool_registry=MagicMock(), llm_adapter=MagicMock())


class TestNormalizeDashboardPayloadLanguage(unittest.TestCase):
    def test_no_dashboard_fallback_summary_is_english(self):
        orch = _make_orchestrator()
        ctx = AgentContext(query="test", stock_code="AAPL", stock_name="Apple")
        ctx.meta["report_language"] = "en"
        ctx.add_opinion(AgentOpinion(agent_name="technical", signal="hold", confidence=0.6))

        normalized = orch._normalize_dashboard_payload({"decision_type": "hold"}, ctx)

        self.assertIn("Multi-agent pipeline", normalized["analysis_summary"])
        self.assertNotRegex(normalized["analysis_summary"], r"[一-鿿]")

    def test_default_time_sensitivity_is_english(self):
        orch = _make_orchestrator()
        ctx = AgentContext(query="test", stock_code="AAPL", stock_name="Apple")
        ctx.meta["report_language"] = "en"
        ctx.add_opinion(AgentOpinion(agent_name="technical", signal="hold", confidence=0.6))

        normalized = orch._normalize_dashboard_payload(
            {"decision_type": "hold", "analysis_summary": "Momentum is flat."}, ctx
        )

        core = normalized["dashboard"]["core_conclusion"]
        self.assertEqual(core["time_sensitivity"], "This week")
        self.assertNotRegex(core["signal_type"], r"[一-鿿]")

    def test_battle_plan_position_strategy_is_english(self):
        orch = _make_orchestrator()
        ctx = AgentContext(query="test", stock_code="AAPL", stock_name="Apple")
        ctx.meta["report_language"] = "en"
        ctx.add_opinion(AgentOpinion(agent_name="technical", signal="buy", confidence=0.8))

        normalized = orch._normalize_dashboard_payload(
            {"decision_type": "buy", "analysis_summary": "Breaking out."}, ctx
        )

        strategy = normalized["dashboard"]["battle_plan"]["position_strategy"]
        self.assertNotRegex(strategy["suggested_position"], r"[一-鿿]")
        self.assertNotRegex(strategy["risk_control"], r"[一-鿿]")
        self.assertIn("Stop Loss", strategy["risk_control"])

    def test_zh_default_unaffected(self):
        orch = _make_orchestrator()
        ctx = AgentContext(query="test", stock_code="600000", stock_name="浦发银行")
        ctx.meta["report_language"] = "zh"
        ctx.add_opinion(AgentOpinion(agent_name="technical", signal="hold", confidence=0.6))

        normalized = orch._normalize_dashboard_payload({"decision_type": "hold"}, ctx)

        self.assertIn("多 Agent 未生成完整仪表盘", normalized["analysis_summary"])
        core = normalized["dashboard"]["core_conclusion"]
        self.assertEqual(core["time_sensitivity"], "本周内")


class TestMarkPartialDashboardLanguage(unittest.TestCase):
    def test_degraded_prefix_is_english(self):
        orch = _make_orchestrator()
        tagged = orch._mark_partial_dashboard(
            {"analysis_summary": "Momentum is flat."},
            note="Multi-agent pipeline timed out.",
            language="en",
        )
        self.assertTrue(tagged["analysis_summary"].startswith("[Degraded result]"))
        self.assertNotRegex(tagged["analysis_summary"], r"[一-鿿]")

    def test_degraded_prefix_is_chinese_by_default(self):
        orch = _make_orchestrator()
        tagged = orch._mark_partial_dashboard(
            {"analysis_summary": "动量平稳。"},
            note="多 Agent 超时，以下结论基于已完成阶段自动降级生成。",
        )
        self.assertTrue(tagged["analysis_summary"].startswith("[降级结果]"))


class TestBuildDataPerspectiveLanguage(unittest.TestCase):
    def test_bias_status_and_chip_health_are_english(self):
        orch = _make_orchestrator()
        ctx = AgentContext(query="test", stock_code="AAPL", stock_name="Apple")
        ctx.meta["report_language"] = "en"
        ctx.set_data("trend_result", {"bias_ma5": 8})
        ctx.set_data("chip_distribution", {})

        data_perspective = orch._build_data_perspective(ctx, {}, "en")

        self.assertEqual(data_perspective["price_position"]["bias_status"], "Overbought")
        self.assertEqual(data_perspective["chip_structure"]["chip_health"], "Average")

    def test_bias_status_and_chip_health_are_chinese_by_default(self):
        orch = _make_orchestrator()
        ctx = AgentContext(query="test", stock_code="600000", stock_name="浦发银行")
        ctx.meta["report_language"] = "zh"
        ctx.set_data("trend_result", {"bias_ma5": 8})
        ctx.set_data("chip_distribution", {})

        data_perspective = orch._build_data_perspective(ctx, {})

        self.assertEqual(data_perspective["price_position"]["bias_status"], "超买")
        self.assertEqual(data_perspective["chip_structure"]["chip_health"], "一般")


class TestRiskOverrideLanguage(unittest.TestCase):
    def _ctx_with_buy_veto(self, language: str) -> AgentContext:
        ctx = AgentContext(query="test", stock_code="AAPL", stock_name="Apple")
        ctx.meta["report_language"] = language
        ctx.add_opinion(
            AgentOpinion(
                agent_name="risk",
                signal="hold",
                confidence=0.7,
                raw_data={"veto_buy": True, "reasoning": "High risk detected"},
            )
        )
        ctx.add_opinion(AgentOpinion(agent_name="decision", signal="buy", confidence=0.8))
        ctx.set_data(
            "final_dashboard",
            {
                "decision_type": "buy",
                "operation_advice": "买入",
                "analysis_summary": "Strong breakout expected.",
                "sentiment_score": 70,
                "dashboard": {
                    "core_conclusion": {
                        "one_sentence": "Buy now on the breakout.",
                        "position_advice": {},
                    }
                },
            },
        )
        return ctx

    def test_risk_override_rewrites_to_english(self):
        orch = _make_orchestrator()
        ctx = self._ctx_with_buy_veto("en")

        orch._apply_risk_override(ctx)

        dashboard = ctx.get_data("final_dashboard")
        self.assertEqual(dashboard["decision_type"], "hold")
        self.assertNotRegex(dashboard["risk_warning"], r"[一-鿿]")
        self.assertNotRegex(dashboard["analysis_summary"], r"[一-鿿]")

        core = dashboard["dashboard"]["core_conclusion"]
        self.assertNotRegex(core["signal_type"], r"[一-鿿]")
        self.assertNotRegex(core["one_sentence"], r"[一-鿿]")
        self.assertNotRegex(core["position_advice"]["no_position"], r"[一-鿿]")
        self.assertNotRegex(core["position_advice"]["has_position"], r"[一-鿿]")

    def test_risk_override_stays_chinese_by_default(self):
        orch = _make_orchestrator()
        ctx = self._ctx_with_buy_veto("zh")

        orch._apply_risk_override(ctx)

        dashboard = ctx.get_data("final_dashboard")
        self.assertIn("风控接管", dashboard["risk_warning"])
        core = dashboard["dashboard"]["core_conclusion"]
        self.assertEqual(core["signal_type"], "🟡持有观望")


if __name__ == "__main__":
    unittest.main()
