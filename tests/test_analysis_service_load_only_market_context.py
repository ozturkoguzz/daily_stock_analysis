# -*- coding: utf-8 -*-
"""Analyze must not generate the market review.

The daily market review is generated once/day by the scheduled bot job; every
/analyze call should only *load* the cached same-day context, never generate it
(generation is slow + costly and would land on a random user). So the analyze
pipeline is constructed with daily_market_context_allow_generate=False.
"""
import unittest
from unittest.mock import MagicMock, patch

from src.services.analysis_service import AnalysisService


class TestAnalyzeIsMarketContextLoadOnly(unittest.TestCase):
    def test_pipeline_built_with_allow_generate_false(self) -> None:
        service = AnalysisService()
        fake_pipeline = MagicMock()
        fake_pipeline.process_single_stock.return_value = None  # short-circuits after build

        with patch(
            "src.core.pipeline.StockAnalysisPipeline",
            return_value=fake_pipeline,
        ) as pipeline_cls:
            service.analyze_stock("AAPL", send_notification=False)

        _, kwargs = pipeline_cls.call_args
        self.assertIs(kwargs.get("daily_market_context_allow_generate"), False)


if __name__ == "__main__":
    unittest.main()
