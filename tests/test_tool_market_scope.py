# -*- coding: utf-8 -*-
"""Tools that only have A-share data must not be offered for US analyses.

Measured on production logs: the agent repeatedly called get_chip_distribution
on US tickers (AAPL, QCOM, HIMS, GLW). 筹码分布 has no US data source, so every
call failed -- and each one still consumed an agent step. 28 runs logged
"Agent hit max steps", i.e. the analysis was truncated while steps were being
spent on tools that cannot work.

Verified live before writing this:
    get_capital_flow('MRVL')      -> status=not_supported,
                                     "only available for A-share stocks"
    get_chip_distribution('MRVL') -> "No chip distribution data available"
    get_sector_rankings()         -> Chinese sector names, no region parameter
"""

import unittest

from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolPolicy
from src.agent.tools.market_scope import (
    CN_ONLY_TOOLS,
    market_for_scope,
    tools_for_market,
)


def _tool(name: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="x",
        parameters=[ToolParameter(name="stock_code", type="string", description="x")],
        handler=lambda **_: {},
        category="data",
        policy=ToolPolicy.unknown(),
    )


class _Scope:
    def __init__(self, codes):
        self.allowed_stock_codes = set(codes)


class TestMarketForScope(unittest.TestCase):
    def test_us_tickers_resolve_to_us(self) -> None:
        for code in ("AAPL", "MRVL", "TSLA", "OSCR"):
            self.assertEqual(market_for_scope(_Scope([code])), "us", code)

    def test_a_share_codes_resolve_to_cn(self) -> None:
        for code in ("600519", "000001", "SH600519"):
            self.assertEqual(market_for_scope(_Scope([code])), "cn", code)

    def test_no_scope_is_unknown(self) -> None:
        self.assertIsNone(market_for_scope(None))

    def test_empty_scope_is_unknown(self) -> None:
        self.assertIsNone(market_for_scope(_Scope([])))

    def test_mixed_scope_is_unknown(self) -> None:
        # Never guess when the run covers more than one market.
        self.assertIsNone(market_for_scope(_Scope(["AAPL", "600519"])))


class TestToolsForMarket(unittest.TestCase):
    def setUp(self) -> None:
        self.all = [_tool(n) for n in
                    ["get_daily_history", "analyze_trend", *sorted(CN_ONLY_TOOLS)]]

    def test_us_run_drops_cn_only_tools(self) -> None:
        kept = {t.name for t in tools_for_market(self.all, "us")}
        self.assertIn("get_daily_history", kept)
        self.assertIn("analyze_trend", kept)
        for name in CN_ONLY_TOOLS:
            self.assertNotIn(name, kept, f"{name} has no US data and wastes an agent step")

    def test_cn_run_keeps_everything(self) -> None:
        kept = {t.name for t in tools_for_market(self.all, "cn")}
        self.assertEqual(kept, {t.name for t in self.all})

    def test_unknown_market_keeps_everything(self) -> None:
        # Fail open: a market we cannot resolve must not silently lose tools.
        kept = {t.name for t in tools_for_market(self.all, None)}
        self.assertEqual(kept, {t.name for t in self.all})

    def test_the_cn_only_set_is_what_we_measured(self) -> None:
        self.assertEqual(
            CN_ONLY_TOOLS,
            {"get_chip_distribution", "get_capital_flow", "get_sector_rankings"},
        )


class TestRunLoopWithholdsCnOnlyToolsFromUsRuns(unittest.TestCase):
    """The filter has to reach the declarations actually sent to the LLM."""

    def _decls_for(self, codes):
        from unittest.mock import MagicMock
        from src.agent import runner as runner_mod
        from src.agent.tools.registry import ToolRegistry

        registry = ToolRegistry()
        for name in ["get_daily_history", "analyze_trend", *sorted(CN_ONLY_TOOLS)]:
            registry.register(_tool(name))

        seen = {}

        class _Adapter:
            def call_with_tools(self, messages, tool_decls, timeout=None):
                seen["tools"] = list(tool_decls or [])
                return MagicMock(content="done", tool_calls=None, usage={},
                                 provider="p", model="m")

        adapter = _Adapter()
        try:
            runner_mod.run_agent_loop(
                messages=[{"role": "user", "content": "hi"}],
                tool_registry=registry,
                llm_adapter=adapter,
                max_steps=1,
                stock_scope=_Scope(codes) if codes is not None else None,
                emit_stage_events=False,
            )
        except Exception:
            pass  # the loop internals are not under test; the tool list is
        return {t.get("function", {}).get("name") for t in seen.get("tools", [])}

    def test_us_scoped_run_never_offers_cn_only_tools(self) -> None:
        names = self._decls_for(["AAPL"])
        self.assertTrue(names, "adapter was never called - test is not exercising the loop")
        for cn_tool in CN_ONLY_TOOLS:
            self.assertNotIn(cn_tool, names)
        self.assertIn("analyze_trend", names)

    def test_cn_scoped_run_still_offers_them(self) -> None:
        names = self._decls_for(["600519"])
        self.assertTrue(names, "adapter was never called - test is not exercising the loop")
        self.assertIn("get_chip_distribution", names)


if __name__ == "__main__":
    unittest.main()
