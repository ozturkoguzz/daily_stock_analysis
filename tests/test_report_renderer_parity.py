# -*- coding: utf-8 -*-
"""Regression test: NotificationService.generate_dashboard_report() and
HistoryService._generate_single_stock_markdown() are two hand-copied
implementations of the same "full report" format. Every time one gets a fix
(score line, confidence/trust block, honest volume ratio, full one-liner) the
other one is at risk of silently drifting behind it — as happened with the
bot-facing history_service.py copy.

This test builds one representative payload and renders it through BOTH
renderers, asserting both surfaces show: the sentiment score, the
confidence/trust block text, a real (non-"N/A") volume ratio with an honest
"(5d)" label, and the complete one-liner with no truncation.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Keep this test runnable when optional LLM/runtime deps are not installed.
for optional_module in ("litellm", "json_repair"):
    try:
        __import__(optional_module)
    except ModuleNotFoundError:
        sys.modules[optional_module] = mock.MagicMock()

from src.agent.orchestrator import _truncate_text
from src.analyzer import AnalysisResult
from src.config import Config
from src.notification import NotificationService
from src.services.history_service import HistoryService


def _make_config(**overrides) -> Config:
    return Config(stock_list=[], **overrides)


class _MockRecord:
    created_at = None
    code = "AVGO"
    name = "Broadcom"
    sentiment_score = 39
    trend_prediction = ""
    operation_advice = ""
    analysis_summary = ""
    news_content = ""


LONG_ONE_SENTENCE = (
    "AVGO is experiencing a short-term bearish correction, trading below its key "
    "moving averages amid broad technology sector weakness, but a potential double "
    "bottom pattern near support keeps a cautious watch warranted before chasing strength."
)


def _make_result() -> AnalysisResult:
    return AnalysisResult(
        code="AVGO",
        name="Broadcom",
        sentiment_score=39,
        trend_prediction="Bearish",
        operation_advice="Hold",
        decision_type="hold",
        confidence_level="Medium",
        report_language="en",
        analysis_summary=LONG_ONE_SENTENCE,
        dashboard={
            "core_conclusion": {"one_sentence": LONG_ONE_SENTENCE},
            "phase_decision": {
                "action_window": "Watch the upcoming market open.",
                "immediate_action": "Wait for intraday confirmation; do not chase.",
                "next_check_time": "2026-07-20 09:30 AM EST",
                "confidence_reason": "Confidence is capped at Medium due to fallback quote data.",
                "watch_conditions": [],
                "data_limitations": ["quote: fallback"],
            },
            "data_perspective": {
                "volume_analysis": {
                    "volume_ratio": "N/A",
                    "volume_ratio_5d": 1.2135159243119937,
                    "volume_status": "normal",
                    "turnover_rate": "N/A",
                    "volume_meaning": "Volume is unremarkable.",
                },
            },
        },
    )


class TestReportRendererParity(unittest.TestCase):
    @mock.patch("src.notification.get_config")
    def test_both_renderers_show_score_confidence_volume_and_full_one_liner(
        self, mock_get_config: mock.MagicMock
    ):
        mock_get_config.return_value = _make_config(report_renderer_enabled=False)

        notification_out = NotificationService().generate_dashboard_report(
            [_make_result()], report_date="2026-07-20"
        )
        history_out = HistoryService.__new__(HistoryService)._generate_single_stock_markdown(
            _make_result(), _MockRecord()
        )

        for label, out in (("notification.py", notification_out), ("history_service.py", history_out)):
            with self.subTest(renderer=label):
                # Task 1: sentiment score
                self.assertIn("39/100", out)
                # Task 2: confidence / trust block
                self.assertIn("capped at Medium due to fallback quote data", out)
                # Task 3: honest volume ratio, not "N/A"
                self.assertIn("1.21 (5d)", out)
                self.assertNotIn("Ratio N/A", out)
                # Task 4: full one-liner, not truncated mid-word
                self.assertIn(LONG_ONE_SENTENCE, out)


class TestTruncateTextWordBoundary(unittest.TestCase):
    def test_breaks_on_word_boundary_not_mid_word(self):
        text = "AVGO is experiencing a short-term bearish correction amid weakness"
        truncated = _truncate_text(text, 30)
        self.assertTrue(truncated.endswith("…"))
        # Must not cut in the middle of a word (e.g. "short-…" or "correc…"):
        # the character right after the kept body in the original text must
        # be a space (a real word boundary), not more letters of a word.
        body = truncated[:-1].rstrip()
        self.assertTrue(text.startswith(body))
        next_char = text[len(body):len(body) + 1]
        self.assertIn(next_char, ("", " "))

    def test_short_text_is_unchanged(self):
        self.assertEqual(_truncate_text("short", 60), "short")

    def test_prefers_sentence_boundary_over_dangling_word(self):
        # A complete sentence that fits should end the output cleanly — no "…"
        # dangling on a trailing function word ("...marked by a…").
        text = (
            "JPM maintains a robust bullish structure. "
            "However, short-term momentum has slowed, marked by a MACD death cross."
        )
        truncated = _truncate_text(text, 60)
        self.assertEqual(truncated, "JPM maintains a robust bullish structure.")
        self.assertFalse(truncated.endswith("…"))

    def test_falls_back_to_word_boundary_when_no_sentence_fits(self):
        # First sentence longer than the limit: no full sentence fits, so keep
        # the word-boundary + ellipsis behaviour.
        text = "JPM maintains a robust medium-term bullish moving-average structure overall"
        truncated = _truncate_text(text, 30)
        self.assertTrue(truncated.endswith("…"))
        body = truncated[:-1].rstrip()
        self.assertIn(text[len(body):len(body) + 1], ("", " "))


if __name__ == "__main__":
    unittest.main()
