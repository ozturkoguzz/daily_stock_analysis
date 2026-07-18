# -*- coding: utf-8 -*-
"""Regression test: HistoryService markdown must not leak Chinese ma_alignment/
volume_status/time_sensitivity text into EN reports.

The API markdown endpoint (GET /api/v1/history/{id}/markdown) renders through
HistoryService._generate_single_stock_markdown, which duplicates
NotificationService's dashboard rendering logic but historically forgot the
translate_status() wrapping applied on the notification.py path.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.analyzer import AnalysisResult
from src.services.history_service import HistoryService


class _MockRecord:
    created_at = None


class TestHistoryServiceMarkdownLanguage(unittest.TestCase):
    def test_ma_alignment_and_volume_status_translated_for_english(self):
        result = AnalysisResult(
            code="MRVL",
            name="Marvell",
            sentiment_score=65,
            trend_prediction="Bullish",
            operation_advice="Buy",
            decision_type="buy",
            analysis_summary="Uptrend intact.",
            report_language="en",
            dashboard={
                "data_perspective": {
                    "trend_status": {
                        "ma_alignment": "强势多头排列，均线发散上行",
                        "is_bullish": True,
                        "trend_score": 90,
                    },
                    "volume_analysis": {
                        "volume_ratio": 1.5,
                        "volume_status": "放量上涨",
                        "turnover_rate": 2.1,
                    },
                },
                "core_conclusion": {
                    "one_sentence": "Favor buying on strength.",
                },
            },
        )

        markdown = HistoryService.__new__(HistoryService)._generate_single_stock_markdown(
            result, _MockRecord()
        )

        self.assertIn("Strong bullish alignment, MAs diverging upward", markdown)
        self.assertIn("High volume, rising", markdown)
        self.assertEqual(markdown.count("强势多头排列"), 0)
        self.assertEqual(markdown.count("放量上涨"), 0)

    def test_time_sensitivity_default_translated_for_english(self):
        result = AnalysisResult(
            code="MRVL",
            name="Marvell",
            sentiment_score=65,
            trend_prediction="Bullish",
            operation_advice="Buy",
            decision_type="buy",
            analysis_summary="Uptrend intact.",
            report_language="en",
            dashboard={"core_conclusion": {"one_sentence": "Favor buying on strength."}},
        )

        markdown = HistoryService.__new__(HistoryService)._generate_single_stock_markdown(
            result, _MockRecord()
        )

        self.assertIn("This week", markdown)
        self.assertNotIn("本周内", markdown)

    def test_ma_alignment_stays_chinese_by_default(self):
        result = AnalysisResult(
            code="600519",
            name="贵州茅台",
            sentiment_score=65,
            trend_prediction="看多",
            operation_advice="买入",
            decision_type="buy",
            analysis_summary="趋势良好。",
            dashboard={
                "data_perspective": {
                    "trend_status": {
                        "ma_alignment": "强势多头排列，均线发散上行",
                        "is_bullish": True,
                        "trend_score": 90,
                    },
                },
            },
        )

        markdown = HistoryService.__new__(HistoryService)._generate_single_stock_markdown(
            result, _MockRecord()
        )

        self.assertIn("强势多头排列，均线发散上行", markdown)


if __name__ == "__main__":
    unittest.main()
