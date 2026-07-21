# -*- coding: utf-8 -*-
"""Recap date should be the last completed trading session, not datetime.now().

When the scheduled market-review job runs pre-market, datetime.now() would label the
recap with a day whose session has not closed yet (the data is the prior close). The
recap date must come from trading_calendar.get_effective_trading_date(region).
"""
import unittest
from datetime import date
from unittest.mock import patch

from src.market_analyzer import MarketAnalyzer


class TestRecapDateUsesEffectiveTradingDate(unittest.TestCase):
    def test_overview_date_is_effective_trading_date_not_today(self) -> None:
        analyzer = MarketAnalyzer(region="us")
        with patch.object(analyzer, "_get_main_indices", return_value=[]), patch(
            "src.market_analyzer.get_effective_trading_date",
            return_value=date(2026, 7, 17),
        ) as eff:
            overview = analyzer.get_market_overview()

        eff.assert_called_once_with("us")
        self.assertEqual(overview.date, "2026-07-17")


if __name__ == "__main__":
    unittest.main()
